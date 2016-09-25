import urllib
import httplib2
from bs4 import BeautifulSoup
import math
import argparse
from operator import itemgetter

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
		if s.get_text() == str(args.season) + " Gamelog Stats":
			tab = s.parent.parent.parent # td.tr.table
			tab2 = tab.next_sibling.next_sibling
			dataCells = tab2.find_all('td', 'sort1')

			#print dataCells

			i = startIdx
			weekIndex = 0
			while i < len(dataCells):

				if args.duels or args.duel or args.consistency:
					weekStr = dataCells[weekIndex].get_text()
					if weekStr == "DP" or weekStr == "CC" or weekStr == "WC":
						break
					else:
						week = int(weekStr)
					#print "Week: " + str(week)
					if week > 16:
						break

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
					if args.duels or args.duel or args.consistency:
						numPad = week - len(allPts)
						for n in range(numPad - 1):
							allPts.append(0.0)

					allPts.append(fpts)

				i += cellNo + 1
				weekIndex += cellNo + 1

	if args.lastn > 0:
		allPts = allPts[len(allPts) - args.lastn:]

	if args.duels or args.duel or args.consistency:
		return allPts

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

	score = avgPts - (stdDev * args.stddevweight) + bonus * 0.25

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
		"Green Bay Packers" : "GB", "Los Angeles Rams" : "LAR"}

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
	print ptsAllowed
	raise 0.0
	return 0.0

def FilterByWeek(d, week):
	for _, allPts in d.iteritems():
		yield allPts[week] if week < len(allPts) else 0.0

def ConsistencyScore(tab):
	# 90, 75, 50, 25
	return tab[0] * 3 + (tab[1]-tab[0]) * 2 + tab[2] * 1.5 + tab[3] - tab[4]

parser = argparse.ArgumentParser(prog='NFL crawler', usage='%(prog)s [options]')
parser.add_argument("--pos", help="Position (rb/wr/qb/k/te/kperc)", default='wr')
parser.add_argument("--outlierweight", help="Std dev weight to remove outliers (1=1 std dev)", default=1.0, type=float)
parser.add_argument("--stddevweight", help="Std dev weight (used when calculating expected score, avg-x*stddev", \
	default=1.0, type=float)
parser.add_argument("--lastn", help="Only consider last N samples", default = 0, type=int)
parser.add_argument("--rejectonlyposoutliers", help="Only reject positive outliers", action='store_true')
parser.add_argument("--minsamples", help="Min samples required", default=2, type=int)
parser.add_argument("--week", help="Week - adjust score by opponent's team score per given week", type=int)
parser.add_argument("--pts_over_avg", help="Show pts over average", action='store_true')
parser.add_argument("--pts_over_pos", help="Show pts over given pos", default=0, type=int)
parser.add_argument("--duels", help="Compare scores week by week", action='store_true')
parser.add_argument("--duel", help="Compare scores week by week, for 2 players (--duel PLAYER1 PLAYER2)", nargs=2)
parser.add_argument("--consistency", help="Calc week-by-week consistency", action='store_true')
parser.add_argument("--season", help="Season (2015, 2016, etc)", default=2016, type=int)
args = parser.parse_args()

# Format: pos ID (url), index of fpts in the player's table, no of fields in the summary table
posDatum = { "rb" : [20, 12, 12], "wr" : [30, 12, 12], "qb" : [10, 13, 13], "k" : [80, 8, 10], "te" : [40, 8, 9], \
	"kperc" : [80, 8, 10], "def" : [99, 12, 13] }
posData = posDatum[args.pos]
posID = posData[0]
fptsCellNo = posData[1]

h = httplib2.Http()
url = 'http://fftoday.com/stats/playerstats.php?Season=' + str(args.season) + \
	'&GameWeek=&PosID=' + str(posID) + '&order_by=FFPtsPerG'
print url

(resp_headers, content) = h.request(url, "GET")
			
soup = BeautifulSoup(content)
#print soup

dataCells = soup.find_all('td', 'sort1')
#print dataCells

if args.week:
	year = args.season - 2000 # 2016 -> 16
	gameMatrix = BuildGameMatrix(h, "/nfl/schedule_grid_" + str(year) + ".htm")
	ptsAllowed = BuildPointsAllowedMatrix(h, "/stats/fantasystats.php?Season=" + str(args.season) + \
		"&GameWeek=Season&PosID=" + str(posID) + "&Side=Allowed")

i = 0
allScores = []
minDev = 100.0
minDevName = ""
totalScore = 0.0
playerPoints = {}
while i < len(dataCells):
	#print dataCells[i]
	team = dataCells[i + 1].get_text().strip()
	links = dataCells[i].find_all('a')
	bonus = 0.0
	if args.week:
		opp = FindOpponent(gameMatrix, team, args.week)
		bonus = FindTeamBonus(ptsAllowed, opp)
		print team + " - playing " + opp + " - bonus: " + str(bonus)

	href = links[0]['href']
	name = links[0].get_text()
	print name

	if args.duels or args.duel or args.consistency:
		if not args.duel or args.duel[0] == name or args.duel[1] == name:
			playerPoints[name] = ParsePlayer(h, href, args, fptsCellNo, bonus)
	else:
		score, stdDev = ParsePlayer(h, href, args, fptsCellNo, bonus)

		totalScore += score

		if stdDev < minDev:
			minDev = stdDev
			minDevName = name

		allScores.append((name, score))
	
	i += posData[2]

if args.consistency:

	consistencyData = {}

	for week in range(0, 16):
		print("Week " + str(week + 1))

		weekPts = sorted([p for p in FilterByWeek(playerPoints, week) if p > 0])
		print weekPts
		if len(weekPts) == 0:
			break

		median = weekPts[len(weekPts) / 2]
		q75 = weekPts[len(weekPts) * 3 / 4]
		q25 = weekPts[len(weekPts) / 4]
		q90 = weekPts[len(weekPts) * 9 / 10]

		for pn, allPts in playerPoints.iteritems():
			cdata = consistencyData.get(pn, [0, 0, 0, 0, 0])
			thisWeekPts = allPts[week] if week < len(allPts) else 0
			if thisWeekPts > q90:
				cdata[0] = cdata[0] + 1
			if thisWeekPts > q75:
				cdata[1] = cdata[1] + 1
			if thisWeekPts > median:
				cdata[2] = cdata[2] + 1
			if thisWeekPts > q25:
				cdata[3] = cdata[3] + 1
			else:
				cdata[4] = cdata[4] + 1

			consistencyData[pn] = cdata

	scores = { pn : ConsistencyScore(cd) for pn, cd in consistencyData.iteritems() }

	for s in sorted(scores.iteritems(), key = itemgetter(1), reverse=True):
		print(str(s[0]) + " - " + str(s[1]) + " - " + str(consistencyData[s[0]]))

elif args.duel:
	ptsA = playerPoints[args.duel[0]]
	ptsB = playerPoints[args.duel[1]]

	print ptsA
	print ptsB

	winsA = [ x - y for x, y in zip(ptsA, ptsB) ]
	numWinsA = sum(1 for c in winsA if c > 0)
	print args.duel[0] + " " + str(numWinsA) + " wins"
	print args.duel[1] + " " + str(len(ptsA) - numWinsA) + " wins"

	print CalcStdDev(ptsA)
	print CalcStdDev(ptsB)

elif args.duels:
	names = playerPoints.keys()
	wins = {}
	games = {}
	for i, name in enumerate(names):
		print "----------------------------"
		print "Evaluating " + name
		for week, score in enumerate(playerPoints[name]):
			print "Week: " + str(week) + ", score=" + str(score)
			scoreOther = 0.0
			j = i + 1
			while j < len(names):
				otherName = names[j]

				otherScores = playerPoints[otherName]
				otherScore = otherScores[week] if week < len(otherScores) else 0.0
				print "Dueling " + otherName + ", score=" + str(otherScore)

				winner = name if score > otherScore else otherName
				pts = 1 if abs(score - otherScore) < 5 else 1
				wins[winner] = wins.get(winner, 0) + pts
				games[name] = games.get(name, 0) + 1
				games[otherName] = games.get(otherName, 0) + 1

				j = j + 1

	print wins

	for w in sorted(wins.iteritems(), key = itemgetter(1), reverse=True):
		print(str(w[0]) + " - " + str(w[1]) + "(" + str(games[w[0]]) + ")")

else:	
	avgScore = totalScore / len(allScores)
	compScore = avgScore

	# RB/WR = ~50
	# TE = 21
	# QB = 22
	# (15 rounds)
	# 8 rounds - 30 RB, 30 WR, 14 QB, 9 TE, 6 K, 7 DEF

	if args.pts_over_pos > 0:
		allScores = sorted(allScores, reverse=True, key=lambda x: x[1])
		p = args.pts_over_pos
		if p >= len(allScores):
			p = len(allScores) - 1
		compScore = allScores[p][1]

	if args.pts_over_avg or args.pts_over_pos > 0:
		allScores = [ (name, s - compScore) for (name, s) in allScores ]
		#print allScores

	for s in sorted(allScores, reverse=True, key=lambda x: x[1]):
		print("{0} : {1:.2f} : {2}".format(s[0], s[1], args.pos))

	print("Smallest std dev: " + minDevName + " - " + str(minDev))
