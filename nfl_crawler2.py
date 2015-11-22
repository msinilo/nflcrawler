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


def ParsePlayer(h, url, args, cellNo):

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

	score = avgPts - (stdDev * args.stddevweight)

	return score, stdDev

parser = argparse.ArgumentParser(prog='NFL crawler', usage='%(prog)s [options]')
parser.add_argument("--pos", help="Position", default='wr')
parser.add_argument("--outlierweight", help="Std dev weight to remove outliers", default=1.0, type=float)
parser.add_argument("--stddevweight", help="Std dev weight", default = 1.0, type=float)
parser.add_argument("--lastn", help="Only consider last N samples", default = 0, type=int)
parser.add_argument("--rejectonlyposoutliers", help="Only reject positive outliers", action='store_true')
parser.add_argument("--minsamples", help="Min samples required", default=4, type=int)
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

i = 0
allScores = []
minDev = 100.0
minDevName = ""
while i < len(dataCells):
	#print dataCells[i]
	links = dataCells[i].find_all('a')
	print links[0].get_text()
	href = links[0]['href']
	#print href
	score, stdDev = ParsePlayer(h, href, args, fptsCellNo)
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
