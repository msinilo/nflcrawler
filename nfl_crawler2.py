import urllib
import httplib2
from bs4 import BeautifulSoup
import math
import argparse

def CalcStdDev(allPts):
	sumPts = sum(allPts)
	avg = sumPts / len(allPts)

	stdDev = (sum((v - avg) ** 2 for v in allPts) / len(allPts)) ** 0.5

	return avg, stdDev

def ParsePlayer(h, url, args, cellNo, bonus):

	(resp_headers, content) = h.request("http://fftoday.com" + url, "GET")
	soup = BeautifulSoup(content)
	#print soup
	spans = soup.find_all('span', 'headerstats')
	#print span

	# Special case (kicker's %)
	startIdx = cellNo
	if args.pos == "kperc":
		startIdx = 3

	allPts = []

	for s in spans:
		if s.get_text() == "2015 Gamelog Stats":
			tab = s.parent.parent.parent # td.tr.table
			tab2 = tab.next_sibling.next_sibling
			dataCells = tab2.find_all('td', 'sort1')

			i = startIdx
			while i < len(dataCells):

				if args.pos == "kperc":
					fgm = float(dataCells[i].get_text())
					fga = float(dataCells[i + 1].get_text())
					epm = float(dataCells[i + 3].get_text())
					epa = float(dataCells[i + 4].get_text())

					# Severe punishment for missed EP
					if epm < epa:
						epm = 0

					att = epa + fga
					made = fgm + epm
					if att > 0:
						fpts = made * 100.0 / att
						allPts.append(fpts)
				else:
					fpts = float(dataCells[i].get_text())
					allPts.append(fpts)


				i += cellNo + 1

	if args.lastn > 0:
		allPts = allPts[len(allPts) - args.lastn:]

	if len(allPts) < args.minsamples:
		return 0.0, 100.0

	avgPts, stdDev = CalcStdDev(allPts)
	print("Avg: " + str(avgPts) + ", dev: " + str(stdDev) + ", npts: " + str(len(allPts)))
	print allPts

	if args.pos == "kperc":
		return avgPts, stdDev

	diffFunc = lambda x: abs(x)
	if args.rejectonlyposoutliers:
		diffFunc = lambda x: x

	filteredPts = [p for p in allPts if diffFunc(p - avgPts) <= stdDev * args.outlierweight ]
	if len(filteredPts) < len(allPts) / 2 or len(filteredPts) < args.minsamples:
		return 0.0, 100.0

	print filteredPts

	avgPts, stdDev = CalcStdDev(filteredPts)
	print("Avg: " + str(avgPts) + ", dev: " + str(stdDev))

	score = avgPts - (stdDev * args.stddevweight) + bonus * 0.5

	return score, stdDev

def BuildGameMatrix(h, url):
	(resp_headers, content) = h.request("http://fftoday.com" + url, "GET")
	soup = BeautifulSoup(content)
	cells = soup.find_all('td', 'tablehdr')
	
	firstCell = None
	for c in cells:
		if c.get_text() == "ARI":
			firstCell = c
			break

	dataTab = firstCell.parent.parent
	rows = dataTab.select('tr')[1:]
	
	gameMatrix = {}
	for r in rows:
		tds = r.select('td')
		team = tds[0].get_text()
		i = 1
		gameMatrix[team] = []
		while i < len(tds):
			opp = tds[i].get_text().replace("@", "")
			gameMatrix[team].append(opp)
			i = i + 1

	return gameMatrix

def FindOpponent(gameMatrix, team, week):
	return gameMatrix[team][week-1]

def GetTeamAbbreviation(name):
	teamMap = { "New Orleans Saints" : "NO", "New York Giants" : "NYG", "New York Jets" : "NYJ", \
		"Tampa Bay Buccaneers" : "TB", "New England Patriots" : "NE", "San Diego Chargers" : "SD", \
		"San Francisco 49ers" : "SF", "St. Louis Rams" : "STL", "Kansas City Chiefs" : "KC", \
		"Green Bay Packers" : "GB" }

	abbr = teamMap.get(name, "")
	#print name + " - " + abbr

	if abbr:
		return abbr

	return name[:3].upper()

def BuildPointsAllowedMatrix(h, url):
	(resp_headers, content) = h.request("http://fftoday.com" + url, "GET")
	soup = BeautifulSoup(content)
	dataCells = soup.find_all('td', 'sort1')

	cellsPerRow = len(dataCells[0].parent.select('td'))

	records = []

	i = 0
	while i < len(dataCells):
		teamStr = dataCells[i].get_text().strip()
		team = teamStr[teamStr.find(' ')+1:teamStr.find('vs')].strip()
		ptsAllowed = float(dataCells[i + cellsPerRow - 1].get_text())

		records.append((team, ptsAllowed))

		i = i + cellsPerRow

	#print records
	med = records[len(records)/2]

	return [(GetTeamAbbreviation(v[0]), v[1]-med[1]) for v in records]

def FindTeamBonus(ptsAllowed, team):

	print("Find team bonus: " + team)

	for p in ptsAllowed:
		if p[0] == team:
			return p[1]

	print("Not found: " + team)
	raise 0.0
	return 0.0

parser = argparse.ArgumentParser(prog='NFL crawler', usage='%(prog)s [options]')
parser.add_argument("--pos", help="Position (rb/wr/qb/k/te/kperc)", default='wr')
parser.add_argument("--outlierweight", help="Std dev weight to remove outliers", default=1.0, type=float)
parser.add_argument("--stddevweight", help="Std dev weight", default = 1.0, type=float)
parser.add_argument("--lastn", help="Only consider last N samples", default = 0, type=int)
parser.add_argument("--rejectonlyposoutliers", help="Only reject positive outliers", action='store_true')
parser.add_argument("--minsamples", help="Min samples required", default=4, type=int)
parser.add_argument("--week", help="Week - adjust score by opponent's score per given week", type=int)
args = parser.parse_args()

# Format: pos ID (url), index of fpts in the player's table, no of fields in the summary table
posDatum = { "rb" : [20, 12, 12], "wr" : [30, 12, 12], "qb" : [10, 13, 13], "k" : [80, 8, 10], "te" : [40, 8, 9], \
	"kperc" : [80, 8, 10] }
posData = posDatum[args.pos]
posID = posData[0]
fptsCellNo = posData[1]

h = httplib2.Http()
url = 'http://fftoday.com/stats/playerstats.php?Season=2015&GameWeek=&PosID=' + str(posID) + '&order_by=FFPtsPerG'
print url

(resp_headers, content) = h.request(url, "GET")
			
soup = BeautifulSoup(content)
#print soup

dataCells = soup.find_all('td', 'sort1')
#print dataCells

if args.week:
	gameMatrix = BuildGameMatrix(h, "/nfl/schedule_grid_15.htm")
	ptsAllowed = BuildPointsAllowedMatrix(h, "/stats/fantasystats.php?Season=2015&GameWeek=Season&PosID=" + str(posID) + "&Side=Allowed")

i = 0
allScores = []
minDev = 100.0
minDevName = ""
while i < len(dataCells):
	#print dataCells[i]
	team = dataCells[i + 1].get_text().strip()
	links = dataCells[i].find_all('a')
	print links[0].get_text()
	bonus = 0.0
	if args.week:
		opp = FindOpponent(gameMatrix, team, args.week)
		bonus = FindTeamBonus(ptsAllowed, opp)
		print team + " - playing " + opp + " - bonus: " + str(bonus)

	href = links[0]['href']
	#print href
	score, stdDev = ParsePlayer(h, href, args, fptsCellNo, bonus)
	name = links[0].get_text()

	if stdDev < minDev:
		minDev = stdDev
		minDevName = name

	allScores.append((name, score))
	
	i += posData[2]
	#break

for s in sorted(allScores, reverse=True, key=lambda x: x[1]):
	print("{0} -- {1:.2f}".format(s[0], s[1]))

print("Smallest std dev: " + minDevName + " - " + str(minDev))
