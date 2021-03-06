######################################
#Code written by: Andrew Wessels 2010#
#------------------------------------#
#This code is used to produce
# and manipulate a sqlite database
# for working with skyglow


#Possibilities:
#use threading...
#	"import pp"
#use PyGPU for processing images on the gpu...
'''
#Useful for getting set up in terminal:
import skyglowdb
reload(skyglowdb); db = skyglowdb.DB("/home/drew/prj/data/", True)
reload(skyglowdb); bdb = skyglowdb.DB("/media/lavag", True)

A test of the slewing frame cleanup, and command chaining:
db.restore().fixPositions(graph=1).graphPositions()
This will restore the db using the backup, fix the data, and show two graphs...
'''

#self.c.execute("create table `glow` (LTime SMALLINT,MSTime SMALLINT,FrameCounter SMALLINT,DroppedFrames SMALLINT,FrameSizeX SMALLINT,FrameSizeY SMALLINT,TargetRange SMALLINT,Altitude SMALLINT,FocusStepOffset SMALLINT,BytesPerPixel SMALLINT,OffsetToImageData SMALLINT,CameraUsed SMALLINT,FilterWheelPosition SMALLINT,FocusMotorIndex SMALLINT,IntegrationTimeNS SMALLINT,TargetDeltaRange SMALLINT,TargetAzimuth INT,TargetElevation INT,TargetLatitude INT,TargetLongitutde INT,TargetAltitude INT,AircraftLatitude INT,AircraftLongitude INT,AircraftAltitude INT)")
#["LTime","MSTime","FrameCounter","DroppedFrames","FrameSizeX","FrameSizeY","TargetRange","Altitude","FocusStepOffset","BytesPerPixel","OffsetToImageData","CameraUsed","FilterWheelPosition","FocusMotorIndex","IntegrationTimeNS","TargetDeltaRange","TargetAzimuth","TargetElevation","TargetLatitude","TargetLongitutde","TargetAltitude","AircraftLatitude","AircraftLongitude","AircraftAltitude"]
#self.c.execute("insert into `glow` VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [round(d[x],1) for x in names])


import time, sys
from datetime import datetime as dt
#i made this one to help with manipulating the time info
import dbtime
import os
import os.path as op
import uavdata as ud
import sqlite3

import math
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

import shutil

#used for vids
import glob
import subprocess

#used for images
from PIL import Image, ImageFont, ImageDraw#, ImageOps, ImageEnhance

import fnmatch, os

class DB:
	rootdir = ""	
	con = None
	c = None

	#use this as a constant...
	irradpcount = 0.105 # nW / cm2 / um  per  count
	fpserror = 5
	default_sigma = 3
	debug = None
	
	tables = {} #set up some table information so i can automate the table creation
	tables['clouds'] = {"fps":1}
	tables['clouds']['vals'] = {"lt":"SMALLINT UNIQUE", "ms":"SMALLINT", "file":"TEXT", "ix":"INT", "mean":"FLOAT", "std":"FLOAT", "min":"SMALLINT", "max":"SMALLINT"}
	tables['clouds']['files'] = []
	
	tables['glow'] = {"fps":60}
	tables['glow']['vals'] = {"lt":"SMALLINT UNIQUE", "ms":"SMALLINT", "az":"SMALLINT", "el":"SMALLINT", "file":"TEXT", "ix":"INT", "mean":"FLOAT", "std":"FLOAT", "min":"SMALLINT", "max":"SMALLINT"}
	tables['glow']['files'] = []

	tables['positions'] = {}
	tables['positions']['vals'] = {"az":"SMALLINT", "el":"SMALLINT", "count":"SMALLINT", "mean":"FLOAT", "std":"FLOAT", "min":"FLOAT", "max":"FLOAT"}
##	self.c.execute("drop table if exists positions")
##	self.c.execute("create table if not exists `positions` (az SMALLINT, el SMALLINT, start INT, end INT, count SMALLINT, mean FLOAT, std FLOAT, min FLOAT, max FLOAT)")

	def __init__(self, rootdir=None, name="sql", debug=False):
		if rootdir == None:
			rootdir = os.path.abspath(os.curdir)
		self.rootdir = rootdir
		self.conn = sqlite3.connect(op.join(self.rootdir, name))
		self.c = self.conn.cursor()
		self.debug = debug

	def __del__(self):
		# Save (commit) any changes
		self.conn.commit()
		# close the cursor, and connection
		self.c.close()
		self.conn.close()

	def locate(self, pattern, root=None, depth=1):
		# it doesn't need to crawl everything, just the first depth.
		# Fix: use os.walk's pruning capabilities to cut off the tree at a certain length...
		if not root:
			root = self.rootdir
		'''Locate all files matching supplied filename pattern in and below supplied root directory.'''
		startinglevel = root.count(os.sep)
		for path, dirs, files in os.walk(os.path.abspath(root), 1):
			level = path.count(os.sep) - startinglevel
			if level >= depth: #(uses "=" because its going from 1 based to 0 based).
				del dirs[:] #prune off this branch
			else:
				for filename in fnmatch.filter(files, pattern):
					yield os.path.join(path, filename)
					
	def findFiles(self, depth = 2):
		start = time.time()
		print "Finding Files"
		cloudloc = op.join(self.rootdir, "clouds")
		if op.isdir(cloudloc):
			self.tables['clouds']['files'][:] = self.locate('*.img', cloudloc, depth)
			self.tables['clouds']['files'].sort()
		skyloc = op.join(self.rootdir, "skyglow")
		if op.isdir(skyloc):
			self.tables['glow']['files'][:] = self.locate('*.img', skyloc, depth)
			self.tables['glow']['files'].sort()
		self.timestamp("Found %s skyglow images, and %s cloud images!"%(len(self.tables['glow']['files']), len(self.tables['clouds']['files'])), start)
		return self

	def backup(self):
		print "Are you sure you want to overwrite any previous backup?"
		answer = raw_input()
		if len(answer) > 0 and answer[0].lower() == "y" or answer == "1":
			shutil.copy(op.join(self.rootdir, 'sql'), op.join(self.rootdir, 'sql.bak'))
			print "Done."
		else:
			print "Unchanged."
		return self

	def restore(self):
		print "Are you sure you want to overwrite the current database with the backup?"
		answer = raw_input()
		if len(answer) > 0 and answer[0].lower() == "y" or answer == "1":
			shutil.copy(op.join(self.rootdir, 'sql.bak'), op.join(self.rootdir, 'sql'))
			print "Done."
		else:
			print "Unchanged."
		return self

	def delete(self):
		print "Are you sure you want to DELETE the current database?"
		answer = raw_input()
		if len(answer) > 0 and answer[0].lower() == "y" or answer == "1":
			os.remove(op.join(self.rootdir, 'sql'))
			self.conn = sqlite3.connect(op.join(self.rootdir, 'sql'))
			self.c = self.conn.cursor()
			print "Done."
		else:
			print "Unchanged."
		return self
	
	def initTable(self, table, rebuild = False):
		if rebuild:
			self.c.execute("drop table if exists "+table)
		tableinfo = self.tables[table]
		#this will give me the table's values along with their sql data type as a string...
		tabletypes = reduce(lambda a,b:"%s,%s"%(a,b),map(lambda a: "%s %s"%(a, tableinfo['vals'][a]), tableinfo['vals']))
		query = "create table if not exists `" + table + "` (" + tabletypes + ")"
		self.c.execute(query)
	
	#wanted to use "merge" but i guess its reserved.
	#this will take a second database and merge their glow tables, then rebuild the derived tables.
	def collect(self, other):
		#TODO:: MERGE IN CLOUD DATA
		print "Adding frames to this database..."
		table = "glow"
		for table in ["glow", "clouds"]:
			grab = self.tables[table]['vals'].keys()
			strgrab = reduce(lambda a,b:a+","+b,grab)
			#self.c.execute("create table if not exists `glow` (lt SMALLINT UNIQUE, ms SMALLINT, az SMALLINT, el SMALLINT, file TEXT, ix INT, mean FLOAT, std FLOAT, min SMALLINT, max SMALLINT)")
			self.initTable(table)
			vals = other.query("select "+strgrab+" from `"+table+"` where exists(SELECT * from `"+table+"`)")
			for val in vals:
				put = reduce(lambda a,b:a+","+b,map(lambda a:"'"+str(val[a])+"'",grab))
				self.c.execute("insert or ignore into `"+table+"` (%s) VALUES(%s)"%(strgrab, put))
			
		self.process()
	
	def sqlDict(self, c = None):
		if c == None:
			c = self.c
		c.row_factory = sqlite3.Row
		ret = list()
		for f in c.fetchall():
			x = 0
			vals = dict()
			for i in f.keys():
				vals[i] = f[x]
				x+=1
			ret.append(vals)
		return ret

	def sqlDataString(self, data, prefix = "", delim=","):
		def doString(prefix, i, val):
			if type(val) == str:
				return "%s%s='%s'"%(prefix, i, val)
			return "%s%s=%s"%(prefix, i, val)
		ret = ''
		first = True
		for i in data:
			if first:
				first = False
			else:
				ret+=delim
			if prefix != "" and prefix[-1] != ".":
				prefix += "."
			if getattr(data[i], '__iter__', False):#this will detect if the thing is iterable
				vals = []
				for val in data[i]:
					vals.append(doString(prefix, i, val))
				ret += "(" + reduce(lambda a,b: str(a)+" or "+str(b),vals) + ")"
			else:
				ret += doString(prefix, i, data[i])
		return ret	#this stuff isn't of any use atm, might be in the future...
	
	'''
	This is a powerful accessor function that allows you to pull specific data from the db.
	The general form is
		The first table name contains the data you want to extract,
		The second table name is used as the condition...
	General Notes:
		Both "one" and "two" (if used) need to be valid table names.
			Change: You can now use several abreviations for the table names...
		"where" can be an SQL string or a dictionary which may contain multiple conditions.
			Also added some special keys available though the "where" dictionary:
			"slewing" (Bool) : 0 = no slewing, 1 = only slewing, None = Default
			"rep" (Bool) : This will attempt to find a representative frame, instead of getting every frame.
			"betweem" (Tuple(first, second)) : Restrict the lt variable of the conditional table to be between a range.
		if "where" is an SQL string, variables should be prefixed with the second table's name if using two tables:
			ex: "passes.rowid = 2 and passes.start = ..."
		"limit" can be specified to limit the number of results
	Examples:
		"get glow frames in pass number 2"
			translates to: db.get("glow", "passes", {"rowid":2})
		"get positions in the night where start = 1268118808"
			translates to: db.get("positions", "nights", {"start":1268118808})
	Reversed:
		"get the passes that include position 3" (only one will exsist)
			translates to: db.get("passes", "positions", {"rowid":3})
	Single table selection:
		"get positions where rowid = 1"
			translates to: db.get("positions", where={"rowid":3})
						  or:	db.get("positions", "", {"rowid":3})
						  or:	db.get("positions", "positions", {"rowid":3})
	More Advanced Queries
		"get positions that start after 1268118808"
			db.get("positions", where="positions.start >= 1268118808")
		"get positions that start before March 12th 2010"
			maketime = str(dbtime.dbtime({"year":2010,"mon":3,"day":12}))
			db.get("positions", where="start <= "+maketime)
			Note: Read the documentation on dbtime for more variation here...
					Also, notice "positions." can be omitted from "positions.start"
						since the query deals with only one table.
	'''
	def get(self, one, two = "", where={}, limit="", alert=False):
		start = time.time()
		single = ("lt", "lt")
		double = ("start", "end")
		vals = {"clouds":single, "glow":single, "positions":double, "passes":double, "nights":double}
		#unfortunately vals.keys() wont work, because it doesn't retain its order.
		chain = ["clouds", "glow", "positions", "passes", "nights"]
		#store some common abreviations that can be used as an alternative to the full table name...
		alias = {"cloud":"clouds","cld":"clouds", "sky":"glow", "glw":"glow", "position":"positions", "pos":"positions", "pass":"passes", "pas":"passes", "night":"nights", "nit":"nights"}
		if two == "":
			two = one
		#this will attempt to set the value of "one" to "alias[one]", otherwise set it to w/e it already is...
		one = alias.get(one, one)
		two = alias.get(two, two)
		if type(where) == dict:
			where = where.copy() #it passes by reference, and im destroying values...
			wherestr = ""
			if where.has_key('slewing'):
				if two == "positions":
					if where['slewing']:
						wherestr += two+".az = 361 and "+two+".el = 361 and "
					else:
						wherestr += two+".az != 361 and "+two+".el != 361 and "
				else:
					#`positions` is the only table with accurate slewing information...
					raise RuntimeError("get: Cannot use 'slewing' flag unless the second table is `positions`...")
				del where['slewing']
			
			if where.get('rep', 0):
				middle = "ROUND(("+two+"."+vals[two][0]+"+"+two+"."+vals[two][1]+")/2, 0)"
				wherestr += one+"."+vals[one][0]+" <= "+middle+" and "+one+"."+vals[one][1]+" >= "+middle + " and "			
			elif one != two:
				try:
					oix = chain.index(one)
					tix = chain.index(two)
				except ValueError:
					raise RuntimeError("get: Table does not exsist.")
				small = one
				big = two
				if oix > tix:
					big = one
					small = two
				wherestr += small+"."+vals[small][0]+" >= "+big+"."+vals[big][0]+" and "+small+"."+vals[small][1]+" <= "+big+"."+vals[big][1]+" and "
			if where.has_key('rep'):
				del where['rep']
			if where.has_key('between'):
				if (type(where['between']) == tuple or type(where['between']) == list):
					wherestr += two+"."+vals[two][0]+" >= "+str(where['between'][0])+" and "+two+"."+vals[two][1]+" <= "+str(where['between'][1])+" and "
				del where['between']
			wherestr += self.sqlDataString(where, prefix=two, delim=" and ")
		else:
			wherestr = where
		if limit != "":
			limit = " limit " + str(limit)
		query = "select "+one+".*,"+one+".rowid from "+one
		if one != two:
			query += ","+two
			if wherestr == "":
				raise RuntimeError("Get: Cant process two tables with no condition.")
		if wherestr[-5:] == " and ":
			wherestr = wherestr[:-5]
		if wherestr != "":
			query += " where "+wherestr
		query += limit
		if self.debug:
			print query
		#old = 'select glow.* from glow, positions where glow.lt <= ROUND((positions.start+positions.end)/2, 0) and glow.lt >= ROUND((positions.start+positions.end)/2, 0) and positions.el != 361 and positions.az != 361 and positions.start >= 15 and positions.end <= 20"'
		#print old, query==old
		if alert:
			self.timestamp("\tQuery Done.", start)
		return self.query(query)

	def getFrameInfo(self, lt, alert = False):
		start = time.time()
		select = "glow.*,positions.std as pos_std,positions.mean as pos_mean,passes.std as pas_std,passes.mean as pas_mean,nights.std as nit_std,nights.mean as nit_mean"
		where = "glow.lt=? and (glow.lt between positions.start and positions.end) and (glow.lt between passes.start and passes.end) and (glow.lt between nights.start and nights.end)"
		ret = self.query("select "+select+" from glow,positions,passes,nights where "+where, (lt,))
		if alert:		
			self.timestamp("\tQuery Done.", start)
		if ret:
			return ret[0]
		else:
			return None

	def getAvgStats(self, start, end, table = "glow"):
		#TODO:: THIS NEEDS TO GET FIXED TO WORK WITH THE NEW SYSTEM...
		if table == "glow":
			return self.query("select sum(mean)/count(lt) as mean, sum(std)/count(lt) as std, sum(min)/count(lt) as min, sum(max)/count(lt) as max from "+table+" where lt>=? and lt<=?", (start,end))[0]
		elif table == "positions" or table == "passes" or table == "nights":
			return self.query("select sum(mean)/count(start) as mean, sum(std)/count(start) as std, sum(min)/count(start) as min, sum(max)/count(start) as max from "+table+" where start>=? and end<=?", (start,end))[0]
		else:
			raise RuntimeError("getAvgStats: Cannot accept table: " + str(table))

	def query(self, query, var = []):
		if len(var) > 0:
			self.c.execute(query, var)
		else:
			self.c.execute(query)
		ret = self.sqlDict()
		# Save (commit) the changes
		self.conn.commit()
		return ret
	
	def timestamp(self, label, start, remains = None):
		def timestr(elapsed, places = 5):
			if elapsed < 1: #use MS
				return "%s ms"%(round(elapsed*1000, places))
			elif elapsed > 60*60: #use hours
				return "%s hours"%(round(elapsed/(60*60), places))
			elif elapsed > 60: #use minutes
				return "%s mins"%(round(elapsed/60, places))
			else: #use seconds
				return "%s secs"%(round(elapsed, places))
		elapsed = time.time()-start
		leftover=""
		if remains:
			leftover = ", Est. %s left"%(timestr(elapsed*remains))
		print "%s (%s%s)"%(label, timestr(elapsed), leftover)
		
	'''
	Builds the database
	It begins the complete process of indexing a drive
	'''
	def build(self, rebuild = False):
		start = time.time()
		print "*Starting to build the database..."
		#if rebuild:
		self.findFiles()
		self.doFrames("glow", rebuild)
		self.doFrames("clouds", rebuild)
		#self.process()
		now = ((time.time() - start)/60)
		self.timestamp("*Hard drive indexing complete!", start)
		return self #allows for chaining

	'''
	You can run this if you want to do all of the post processing procedures,
	but don't need to rebuild the frame tables.
	'''
	def process(self):
		self.doPositions()
		self.redoPositions()
		self.doPasses()
		self.doNights()
		self.doStats()
	
	#although its not particularly necessary, I think it might be nice to store more information about what files were used.
	#i need to store the filenames to start off with, so why not just store it in the db...
	#i'm not sure how i want to utilize this information...
	#THIS IS UNUSED ATM...
	'''
	def doFiles(self, rebuild=False):
		#TODO:: FINISH THIS
		# need to fix the other dependencies... doFrames
		start = time.time()
		print "Searching for IMG files."
		if rebuild:
			self.c.execute("drop table if exists files")
		self.c.execute("create table if not exists `files` (file TEXT UNIQUE, done BOOL)")
		#count = self.query("select count(*) as count from files")[0]['count']
		imgfiles[:] = self.locate('*.img', self.rootdir)
		for x in imgfiles:
			self.c.execute("insert or ignore into files(file, done) values(?, ?)", [x])
		#self.imgfiles.sort()
		self.timestamp("Found %s IMG files."%(len(self.imgfiles)), start)
		return self
	'''
	
	#old slow version, possibly more thorough?
	def doFrames2(self, rebuild = False):
		start = time.time()
		print "Building frames data"
		if rebuild:
			self.c.execute("drop table if exists glow")
		self.c.execute("create table if not exists `glow` (lt SMALLINT UNIQUE, ms SMALLINT, az SMALLINT, el SMALLINT, file TEXT, ix INT, mean FLOAT, std FLOAT, min SMALLINT, max SMALLINT)")
		lastlt = 0
		for i,img in enumerate(self.skyimgs):
			uadata = ud.UAVData(img)
			print "Reading file #%s (Data Entries: %s)"%(i+1 , len(uadata))
			#positions = dict()
			then = time.time()
			for x in range(len(uadata)):
				d = uadata.frame(x)
				az = d['TargetAzimuth']
				el = d['TargetElevation']
				lt = d['LTime']
				ms = d['MSTime']
				#this should take a frame every second
				if lastlt != lt:
					#i need some means of detecting that the file has already been read
					#only check the first few values, don't bother checking after that...
					if x < 125 and not rebuild:#this LT is already in the db
						check = self.get("glow", where={"lt":lt, "ms":ms})
						if check:
							print "\t", op.basename(img), "appears to already be indexed."
							break; #we don't need to do this file...
					dtfl = np.array(d['Data'], dtype='float32')
					tmean = dtfl.mean()*self.irradpcount
					tstd = dtfl.std()*self.irradpcount
					tmin = int(dtfl.min()*self.irradpcount)
					tmax = int(dtfl.max()*self.irradpcount)
					values = [lt, ms, az, el, img, x, tmean, tstd, tmin, tmax]
					#print values
					self.c.execute("insert or ignore into `glow` (lt,ms,az,el,file,ix,mean,std,min,max) VALUES(?,?,?,?,?,?,?,?,?,?)", values)

				lastlt = lt
			self.timestamp("File %s of %s is done."%(i+1, len(self.skyimgs)), then, len(self.skyimgs)-1-i)
			sys.stdout.flush()
		# Save (commit) the changes
		self.conn.commit()
		self.timestamp("Frames done!", start)
		return self #allows for chaining

	#this version saves time by skipping ahead 50 frames per second...
#	def doFrames(self, rebuild = False):
#		#TODO::REMOVE THE ROUND FROM ORIGINAL AZ EL DATA... PUT THIS IN POSITIONS DETECTION
#		#TODO::Devise a better means of detecting if a file is already indexed. It might get stopped in the middle of indexing...
#		#		also: Simple solution is to check the db for the file path.
#		start = time.time()
#		print "Building frames data"
#		if rebuild:
#			self.c.execute("drop table if exists glow")
#		self.c.execute("create table if not exists `glow` (lt SMALLINT UNIQUE, ms SMALLINT, az SMALLINT, el SMALLINT, file TEXT, ix INT, mean FLOAT, std FLOAT, min SMALLINT, max SMALLINT)")
#		lastlt = 0
#		for i,img in enumerate(self.skyimgs):
#			then = time.time()
#			uadata = ud.UAVData(img)
#			print "Reading file #%s (Data Entries: %s)"%(i+1 , len(uadata))
#			x=0
#			#Saves time by skipping about 56 frames, with the assumption that the LT hasn't changed.
#			while x < len(uadata): #by using a while loop i can skip some of the indicies...
#				d = uadata.frame(x)
#				az = d['TargetAzimuth']
#				el = d['TargetElevation']
#				lt = d['LTime']
#				ms = d['MSTime']
#				#this should take a frame every second
#				if lastlt != lt:
#					#i need some means of detecting that the file has already been read
#					#only check the first few values, don't bother checking after that...
#					if x < 125 and not rebuild:#this LT is already in the db
#						check = self.get("glow", where={"lt":lt, "ms":ms}, limit=1)
#						if check:
#							print "\t", op.basename(img), "appears to already be indexed."
#							break; #we don't need to do this file...
#					dtfl = np.array(d['Data'], dtype='float32')
#					tmean = dtfl.mean()*self.irradpcount
#					tstd = dtfl.std()*self.irradpcount
#					tmin = int(dtfl.min()*self.irradpcount)
#					tmax = int(dtfl.max()*self.irradpcount)
#					values = [lt, ms, az, el, img, x, tmean, tstd, tmin, tmax]
#					#print values
#					self.c.execute("insert or ignore into `glow` (lt,ms,az,el,file,ix,mean,std,min,max) VALUES(?,?,?,?,?,?,?,?,?,?)", values)
#					x += 57 #skip ahead a few shy of 60 frames since the camera is recording 60 fps
#
#				lastlt = lt
#				x+=1
#			self.timestamp("File %s of %s is done."%(i+1, len(self.skyimgs)), then, len(self.skyimgs)-1-i)
#			sys.stdout.flush()
#		# Save (commit) the changes
#		self.conn.commit()
#		self.timestamp("Frames done!", start)
#		return self #allows for chaining

	#This should take care of both tables `clouds` and `glow`
	def doFrames(self, table = "glow", rebuild = False):
		start = time.time()
		print "Building "+table+" data"
		self.initTable(table)
		tableinfo = self.tables[table]
		#self.c.execute("create table if not exists `clouds` (lt SMALLINT UNIQUE, ms SMALLINT, file TEXT, ix INT, mean FLOAT, std FLOAT, min SMALLINT, max SMALLINT)")
		lastlt = 0
		imgfiles = []
		if tableinfo['files']:
			imgfiles = tableinfo['files']
		else:
			#raise Warning("doFrames: No files provided. Try running findFiles()...")
			print "\tNo files provided. Try running findFiles()..."
			return
		for i,img in enumerate(imgfiles):
			then = time.time()
			uadata = ud.UAVData(img)
			print "Reading file %s of %s (Data Entries: %s)"%(i+1, len(imgfiles), len(uadata))
			x=0
			#Saves time by skipping about 56 frames, with the assumption that the LT hasn't changed.
			while x < len(uadata): #by using a while loop i can skip some of the indicies...
				d = uadata.frame(x)
				values = {}
				
				#this should take a frame every second
				#if not x%100:
				#	print x, lastlt
				#	self.timestamp("100 done.", then, len(imgfiles)-1-i)
				if lastlt != d['LTime']:
					values['az'] = d['TargetAzimuth']
					values['el'] = d['TargetElevation']
					values['lt'] = d['LTime']
					values['ms'] = d['MSTime']
					values['file'] = img
					values['ix'] = x
					'''
					#i need some means of detecting that the file has already been read
					#only check the first few values, don't bother checking after that...
					if x < 125 and not rebuild:#this LT is already in the db
						check = self.get("clouds", where={"lt":lt, "ms":ms}, limit=1)
						if check:
							print "\t", op.basename(img), "appears to already be indexed."
							break; #we don't need to do this file...
					'''
					dtfl = np.array(d['Data'], dtype='float32')
					values['mean'] = dtfl.mean()*self.irradpcount
					values['std'] = dtfl.std()*self.irradpcount
					values['min'] = int(dtfl.min()*self.irradpcount)
					values['max'] = int(dtfl.max()*self.irradpcount)

					#values = [lt, ms, img, x, tmean, tstd, tmin, tmax]
					#print values
					qkeys = reduce(lambda a,b:"%s,%s"%(a,b), tableinfo['vals'].keys())
					qvals = reduce(lambda a,b:"%s,%s"%(a,b), map(lambda a: "'%s'"%values[a], tableinfo['vals'].keys()))
					query = "insert or ignore into `"+table+"` ("+qkeys+") VALUES("+qvals+")"
					self.c.execute(query)
					#self.c.execute("insert or ignore into `clouds` (lt,ms,file,ix,mean,std,min,max) VALUES(?,?,?,?,?,?,?,?)", values)
					#skip ahead a few shy of 60 frames since the camera is recording at a relatively constant fps
					skip = tableinfo['fps'] - self.fpserror - 1
					if skip > 0:
						x += skip
					#x += 57 

				lastlt = d['LTime']
				x+=1
			self.timestamp("File done.", then, len(imgfiles)-1-i)
			sys.stdout.flush()
		# Save (commit) the changes
		self.conn.commit()
		self.timestamp("Frames done!", start)
		return self #allows for chaining
	
	def doPositions(self):
		print "Detecting positions data"
		start = time.time()
		
		#this will ensure that the logged positions fall into one of these azel positions
		realazel = {}
		realazel['361'] = (361,)
		realazel['90'] = (0,)
		realazel['75'] = (0, 90, 180, 270)
		realazel['60'] = realazel['75'] + (45, 135, 225, 315)
		realazel['30'] = realazel['45'] = realazel['60'] + (22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5)
		
		self.c.execute("drop table if exists positions")
		self.c.execute("create table if not exists `positions` (az SMALLINT, el SMALLINT, start INT, end INT, count SMALLINT, mean FLOAT, std FLOAT, min FLOAT, max FLOAT)")
		frames = self.query("SELECT * from glow order by lt")
		lastel = 0
		lastaz = 0
		lastlt = 0
		startlt = 0
		first = True
		count = 0
		for x in frames:
			count += 1
			az = round(float(x['az']), 1)
			el = round(float(x['el']), 1)
			lt = x['lt']
			if first:
				lastel = el
				lastaz = az
				lastlt = lt
				startlt = lt
				first = False
			if x['mean'] < 25 or not (az in realazel.get(str(el), [])): #static frames
				az = 361
				el = 361
			#this doesnt work because there are errors in the data, so i'll fix the data later
			if az != lastaz or el != lastel: #new position detection
				values = [lastaz, lastel, startlt, lastlt, count]
				self.c.execute("insert into `positions` (az, el, start, end, count) VALUES(?,?,?,?,?)", values)
				startlt = lt
				count = 0
			lastel = el
			lastaz = az
			lastlt = lt
		#catch the last values
		values = [lastaz, lastel, startlt, lastlt, count]
		self.c.execute("insert into `positions` (az, el, start, end, count) VALUES(?,?,?,?,?)", values)
		# Save (commit) the changes
		self.conn.commit()
		self.timestamp("Positions done!", start)
		return self

	#passes will exclude some slewing frames, since slewing frames in between passes cannot be easilly accounted for.
	def doPasses(self):
		print "Detecting passes data"
		start = time.time()
		self.c.execute("drop table if exists passes")
		self.c.execute("create table if not exists `passes` (start INT UNIQUE, end INT UNIQUE, mean FLOAT, std FLOAT, min FLOAT, max FLOAT)")

		#start running some stats
		data = self.query("select rowid,* from `positions` where az!=361 and el!=361 order by start")
		if not data:
			return;
		counts = []
		firstdata = data[0]
		lastdata = data[0]
		#passdata = []
		for i, e in enumerate(data):
			counts.append(e['el'])
			if e['el'] > lastdata['el']: #new pass
				print "pass from: ", firstdata['start'], "to", lastdata['end']
				self.c.execute("insert into `passes` (start, end) values (?,?)", (firstdata['start'], lastdata['end']))
				firstdata = e
			lastdata = e
		self.c.execute("insert into `passes` (start, end) values (?,?)", (firstdata['start'], lastdata['end']))
		print "last pass from: ", firstdata['start'], "to", lastdata['end']
		if self.debug:
			fig = plt.figure()
			ax = fig.add_subplot(111)
			ax.plot(counts)
			plt.show()
		# Save (commit) the changes
		self.conn.commit()
		self.timestamp("Passes done!", start)
		return self

	def doNights(self):
		print "Detecting nights data"
		time_start = time.time()
		self.c.execute("drop table if exists nights")
		self.c.execute("create table if not exists `nights` (start INT UNIQUE, end INT UNIQUE, mean FLOAT, std FLOAT, min FLOAT, max FLOAT)")
		days = self.query("SELECT lt from glow where lt%30=0 group by strftime('%Y-%m-%d', lt, 'unixepoch', 'localtime')")
		#throwing this in just incase there is something before noon on the first detected day...		
		justincase = dbtime.dbtime(days[0]['lt'])
		justincase["day"]-=1
		days.insert(0,{"lt":int(justincase)})
		for x in days:
			local = dbtime.dbtime(x['lt'])
			start = int(local.set({"hour":12, "min":0, "sec":0}))
			local["day"]+=1
			end = int(local)
			format = '%Y-%m-%d %H:%M:%S'
			#print start, end
			#frames = self.query("select count(*) from glow where lt >= ? and lt <= ?", (start, end))
			#print "Found", frames, "elements"
			firstdata = self.query("SELECT lt from glow where ? < lt and lt <= ? order by lt asc limit 1", (start, end))
			lastdata = self.query("SELECT lt from glow where ? < lt and lt <= ? order by lt desc limit 1", (start, end))
			print "Between", dbtime.dbtime(start).strftime(format), "and", dbtime.dbtime(end).strftime(format)
			#print "from", firstdata, "to", lastdata
			if len(firstdata):
				print "   First:", dbtime.dbtime(firstdata[0]['lt']).strftime(format), "Last:", dbtime.dbtime(lastdata[0]['lt']).strftime(format)
				vals = (firstdata[0]['lt'], lastdata[0]['lt'])
				self.query("insert into `nights` (start, end) values (?,?)", vals)
			else:
				print "   Nothing"
		# Save (commit) the changes
		self.conn.commit()
		self.timestamp("Nights done!", time_start)
		return self
			
	def doStats(self):
		print "Completing statistics"
		chain = ["glow", "positions", "passes", "nights"]
		for c in range(1,len(chain)):
			for x in self.query("select *,rowid from "+chain[c]):
				stats = self.getAvgStats(x['start'], x['end'], chain[c-1])
				#print chain[c], stats
				print stats
				self.query("update `"+chain[c]+"` set "+self.sqlDataString(stats)+" where rowid="+str(x['rowid']))
	
	#This function is intended to be used to merge positions
	#data = list of dictionary data from dbh
	#i = index of thing to merge
	#perm = to make the changes permanent (change the database)
	#direction = 
	#	{
	#		 0 : merge both sides
	#		+1 : merge right
	#		-1 : merge left
	#	}
	def merge(self, data, i, direction, perm = True):
		use = 0
		if direction == 0: #do both sides
			use = i+1
		else:
			use = i+(abs(direction)/direction) #i+1 or i-1
		data[i]['az'] = data[use]['az']
		data[i]['el'] = data[use]['el']
		if (direction <= 0):
			data[i]['start'] = data[i-1]['start']
			data[i]['count'] += data[i-1]['count']
		if (direction >= 0):
			data[i]['end'] = data[i+1]['end']
			data[i]['count'] += data[i+1]['count']
		if direction == 0:
			if perm:
				self.c.execute("delete from `positions` where rowid=? or rowid=?",(data[i-1]['rowid'],data[i+1]['rowid']))
			del data[i+1], data[i-1]
		else:
			if perm:
				self.c.execute("delete from `positions` where rowid=?",(data[use]['rowid'],))
			del data[use]
		return data


	def redoPositions(self, perm = True):
		print "Cleaning up positions data"
		start = time.time()
		self.c.execute("select rowid,az,el,count,start,end from `positions` ")
		data = self.sqlDict()
		graph = self.debug
		if not perm:
			graph=True
		if graph:
			#use this later to graph the original data
			original = list()
			for x in data:
				for z in range(x['count']):
					original.append(x['az']+x['el'])
				#original.append(0)
	
		prev = 0
		next = 0
		#this loop will make the algorithm do a few passes
		for passnum in range(6):
			#go through the list of dictionaries
			for i, e in enumerate(data):
				ne = {}
				if i != len(data)-1:
					ne = data[i+1]
				pe = {}
				if i != 0:
					pe = data[i-1]
				#these shouldnt really happen... too often?
				if e.get('az') == ne.get('az') and e.get('el') == ne.get('el'): #same azel as right side
					data = self.merge(data, i, 1, perm)
				elif e.get('az') == pe.get('az') and e.get('el')== pe.get('el'): #same azel as left side
					data = self.merge(data, i, -1, perm)
				if e['count'] < 5: #small fragment that is not a slewing frame
					# i want the first few passes to just fill up the blanks in the slewinglowes
					if passnum < 2:
						if pe.get('az') == ne.get('az') and pe.get('el') == ne.get('el') and pe.get('az') == 361 and pe.get('el') == 361:
							data = self.merge(data, i, 0, perm)
					else:
						if pe.get('az') == ne.get('az') and pe.get('el') == ne.get('el'): #azel on either side are equivalent
							data = self.merge(data, i, 0, perm)
						elif ne.get('az') == 361 and ne.get('el') == 361: #next position is a slewing frame
							data = self.merge(data, i, 1, perm)
						elif pe.get('az') == 361 and pe.get('el') == 361: #prev position is a slewing frame
							data = self.merge(data, i, -1, perm)
						else: #dont know what else to do with you, so just make it into slewing frames
							e['az'] = 361
							e['el'] = 361
					if perm:
						self.c.execute("update `positions` set "+self.sqlDataString(e)+" where rowid=?", (e['rowid'],))

		if graph:
			show = list()
			for x in data:
				for z in range(x['count']):
					show.append(x['az']+x['el'])
				#show.append(0)	
			#draw the graph
			fig = plt.figure()
			ax = fig.add_subplot(111)
			ax.plot(show, linewidth=2)
			ax.plot(original, linewidth=1)
			plt.show()
	
		# Save (commit) the changes
		self.conn.commit()
		self.timestamp("Data cleanup done!", start)
		return self

	#this will create a bar graph representing the positions data.
	#this may be useful when looking for errors.
	def graphPositions(self, slewing = False):
		fig = plt.figure()
		ax = fig.add_subplot(111)
		#this gathers data for the graph
		where = ""
		if not slewing:
			where = " where az != 361 and el != 361"
		data = self.query("select rowid,* from `positions`"+where)
		x = 0
		for e in data:
			y = e['az']+e['el']
			ax.bar(x, y, e['count'])
			x += e['count']
		#draw the graph
		plt.show()
		return self #allows for chaining

	##Start of data products##
	def doDataPoducts(self):
		start = time.time()
		print "*Writing data products."
		self.doDetails()
		self.doPosImgs()
		self.doPassCollages()
		self.timestamp("*Data products done!", start)

	def doDetails(self, fileloc = "detaildata.txt"):
		start = time.time()
		print "Writing details data."
		grab = ['lt', 'el', 'az', 'min', 'max', 'mean', 'std'] #removed ms because its meaningless
		grab += ['pos_mean', 'pos_std'] + ['pas_mean', 'pas_std'] + ['nit_mean', 'nit_std']
		grab += ['file', 'ix']
		spacer = lambda a,b: str(a)+" "+str(b)
		legend = reduce(spacer,grab)+"\n"
		nights = self.get("nights")
		for i,n in enumerate(nights):
			night_start = time.time()
			udir = self.getNightPath({'lt':n['start']}, "documents")# op.join(self.rootdir, "dataproducts")
			tfile = open(op.join(udir, fileloc), "w")
			tfile.write(legend)#write the legend
			for f in self.get("glow", "positions", where={"slewing":0, "between":(n['start'], n['end'])}):
				dat = self.getFrameInfo(f['lt'])
				vals = [] #need to do it one at t a time if i want it in order...
				if dat: #if the thing is empty the loop will have problems...
					for g in grab:
						vals.append(dat[g])
				if vals: #This could be empty. It's a fragmentation due to reassigning slewing frames, and not setting their azel in frames table...
					tfile.write(reduce(lambda a,b: str(a)+" "+str(b),vals)+"\n")
			#tfile.writelines(lines)
			self.timestamp("\tNight complete.", night_start, len(nights)-1-i)
			tfile.close()
		self.timestamp("Details done!", start)

	def doPosImgs(self):
		start = time.time()
		print "Writing position images (scaled by night)."
		#need to loop through the different nights in order to scale it using that nights average...
		nights = self.get("nights")
		for i,n in enumerate(nights):
			p_start = time.time()
			frames = self.get("glow", "positions", {'rep':1, 'slewing':0, 'between':(n['start'],n['end'])})
			print "\tWriting %s frames."%len(frames)
			#opt = {"mean":n['mean'], "std":n['std']}
			#opt['sigma'] = 4
			opt = {"parent":n}
			self.writeImg(frames, "regular", opt)
			self.timestamp("\t%s frames done. (%s/%s)"%(len(frames), i+1, len(nights)), p_start, len(nights)-1-i)
			#self.writeImg("nostar", opt)
		self.timestamp("Position images done!", start)

	def doPassCollages(self):
		start = time.time()
		print "Writing per pass collages (scaled by pass)."
		passes = self.get("passes")
		for i,p in enumerate(passes):
			p_start = time.time()
			#this will give you the "night" information for this pass, it can then be used for scaling if desired.
			#n = self.get("night", "passes", {"rowid":p['rowid']})
			#this will produce representative (non slewing) frames from every position within this pass.
			frames = self.get("glow", "positions", {'rep':1, 'slewing':0, 'between':(p['start'],p['end'])})
			#it is also possible to change the "sigma" which is multiplied by std in order to scale the image.
			#smaller value will end up with a higher contrast image... Larger value washes the image out.
			opt = {"parent": p} #{'sigma':3} 
			#for x in ['mean', 'std', 'min', 'max']: #include min and max for the legend... (isn't used for scaling)
			#	opt[x] = p[x]
			self.writeCollage(frames, "regular", opt)
			self.timestamp("\tCollage %s of %s done."%(i+1, len(passes)), p_start, len(passes)-1-i)
		self.timestamp("Pass collages done!", start)
	
	def doVideo(self):
		#video for each position per night
		#temp folder
		#	|--azel
		#		'-files from each pass
		#	|
		nights = self.get("nights")
		for n in nights:
			f = self.get("glow", where={"between":(n["start"],n["end"])})
			
		#path = self.getNightPath(opt, op.join())
		loc = op.join(self.getNightPath(opt), "temp", azel, self.getFilename(this_opt)) 
	
	#options:
	#temp - makes a temporary path
	#fullpath - skips everything, just returns this...
	#fulldir - uses this as the directory, and appends a filename
	def getImgPath(self, imgtype, imgfilter, opt={}):
		if opt.get('fullpath'):
			return opt.get('fullpath')
		elif opt.get('fulldir'):
			op.join(opt.get('fulldir'), self.getFilename(opt))
		fulldir = self.getNightPath(opt)
		if opt.get('temp'):
			fulldir = op.join(fulldir, "temp")
		fulldir = op.join(fulldir, imgtype, imgfilter)
		if not op.isdir(fulldir):
			  os.makedirs(fulldir)
		return op.join(fulldir, self.getFilename(opt))

	def getFilename(self, opt={}):
		#this is going to build the filename if one isn't provided
		if opt.get('lt') and not opt.get('name'):
			opt['name'] = time.strftime("%Y%m%d-%H%M%S", time.localtime(opt['lt']))
			#if opt.get('ms'):
			#	opt['name'] += '-'+str(opt['ms'])
		else:
			opt['name'] = "default"#all else fails, make the name "default"
		opt['name'] += '-s'+str(opt.get('sigma', self.default_sigma))		
		return opt['name'] + ".png"

	def getNightPath(self, opt={}):
		night = "unknown"
		if opt.get('lt'):
			nit = dbtime.dbtime(opt['lt'])
			nit['hours'] -= 12 #shifting the hours by -12 will ensure that its placed in the proper day folder
			night = nit.strftime("%Y%m%d")
			
		if opt.has_key("fulldir"):
			return opt['fulldir']
		else:
			datadir = op.join(opt.get("rootdir", self.rootdir), "dbProducts")
			nightdir = op.join(datadir, night)
			if opt.get('temp'):
				nightdir = op.join(nightdir, 'temp')
			#typedir = op.join(nightdir, imgtype)
			#filterdir = op.join(typedir, imgfilter)
			if not op.isdir(nightdir):
			  os.makedirs(nightdir)
			return nightdir;#op.join(filterdir, opt['name'])

	'''
	Given a db "glow" entry, this returns the image data as a PIL.Image.Image...
	This is also where filters are applied.
	'''
	def getImg(self, entry, imgfilter = "regular", opt={}):
		filters = {"histo":self.imgHisto, "regular":self.imgRegular, "nostar":self.imgNostar}
		if not imgfilter.lower() in filters:
			raise RuntimeError('writeimage: Invalid image type. Valid entries:', filters.keys())

		#path = self.filepath(entry, imgfilter, opt)
		#The scaling options might be different, so this might not be a good idea...
		#if op.isfile(path):
		#	return Image.open(path)
		#open the file
		uadata = ud.UAVData(entry['file'])
		fm = uadata.frame(entry['ix'])
		#make it into a numpy array
		dtfl = np.array(fm['Data'], dtype='float32')
		dtfl *= self.irradpcount
		dtfl.shape = (fm['FrameSizeY'], fm['FrameSizeX'])

		opt = opt.copy() #don't change the original
		#determine scaling options
		if not opt.has_key('min') and not opt.has_key('max'):
			opt['sigma'] = opt.get('sigma', self.default_sigma)
			if opt.has_key('parent'):
				parent = opt['parent']
				opt['min'] = parent['mean']-parent['std']*opt['sigma']
				opt['max'] = parent['mean']+parent['std']*opt['sigma']
			else:
				opt['min'] = dtfl.mean()-dtfl.std()*opt['sigma']
				opt['max'] = dtfl.mean()+dtfl.std()*opt['sigma']
		if opt['min'] < 0:
			opt['min'] = 0
		
		use = filters[imgfilter](dtfl, opt) #apply the appropriate filter

		#use = np.clip(dtfl,opt['mean']-opt['std']*opt['sigma'],opt['mean']+opt['std']*opt['sigma'])
		
		if opt.has_key('graph'):
			fig = plt.figure()
			ax = fig.add_subplot(111)
		
			ax.plot(use)
			stats = opt.get('parent', entry)
			ax.plot([stats['mean']+stats['std']]*len(use), linewidth=2, color="b")
			ax.plot([stats['mean']-stats['std']]*len(use), linewidth=2, color="b")
	
			ax.plot([opt['min']]*len(use), linewidth=2, color="r")
			ax.plot([opt['max']]*len(use), linewidth=2, color="r")	
			plt.show()
		
		#stretch values across 0-255
		#tmin = use.min()
		#tmax = use.max()
		use = self.imgScale(use, opt['min'], opt['max'])
		return Image.fromarray(np.array(use, dtype='uint8'))

	#Purpose: pull image data from IMG files, write out images as png after applying a filter.
	# entry = img data from sql
	#  - may be in sqlDict() form: [{'file':"file/loc.img", 'ix':123}, {'file':"file/loc.img", 'ix':321}, ...]
	#  - or it may be a single dictionary in the form: {'file':"file/loc", 'ix':123}
	#  - "file", and "ix" are required fields
	# imgfilter defines which filter to use (useful for different scaling methods)
	#  - can be either "regular" or "nostar" (possibly more to come)
	# opt is a generic dictionary that contains information that is to be used for scaling, and saving the file.
	#		ex: opt = dict('mean':None, 'std':None, 'thresh':5, 'dir':None, 'name':None ...)
	# Scaling options
	#		These options are used for "regular" scaling:
	#		mean - The mean of the image data, this may be an average mean.
	#		std - Standard deviation of the image, this may be an average std.
	#			If not specified, mean and std will be automatically determined.
	#		thresh - This is the multiplier that determines how many times standard deviation the image data should be cropped at.
	#			Default: 5
	# Naming options
	#		rootdir - the directory where the file tree should go. Default is '...rootdir/dataproducts'
	#		fulldir - if set, this will be the exact directory where the image will be placed.
	#		name - This is the filename you want to use. 
	#					If not specified it tries to produce one, if it can't it will produce "default.png"
	def writeImg(self, entries, imgfilter="regular", opt={}):
		start = time.time()
		use = entries
		if type(entries) != list:
			use = [entries]
		img = None
		for entry in use:
			this_opt = opt.copy()
			if type(entry) == dict and entry.has_key("file"):#if just given one entry put it in a list...
				img = self.getImg(entry, imgfilter, opt)
				this_opt['lt'] = opt.get("lt", entry.get("lt", None))
				this_opt['ms'] = opt.get("ms", entry.get("ms", None))
			elif isinstance(entry,Image.Image):
				img = entry
				this_opt['lt'] = opt.get("lt", None)
				this_opt['ms'] = opt.get("ms", None)		
			else:
				raise RuntimeError("writeImg: Invalid entry field.")	
			
			#this is going to build the file path if one isn't provided
			path = self.getImgPath("images", imgfilter, this_opt)
			#print path
			img.save(path)
		#self.timestamp("\t%s %s images done."%(len(entries),imgfilter), start)
		return self #allows for chaining
	
	def writeCollage(self, entries, imgfilter = "regular", opt = {}):
		if type(entries) != list:
			raise RuntimeError("writeCollage: \"entires\" must be a list of db entries.")
		this_opt = opt.copy()
		this_opt['lt'] = opt.get('lt', entries[0]['lt'])
		path = self.getImgPath("collages", imgfilter, this_opt)
		
		#somewhat cheap hack for now:
		dimentions = (2940,2940)
		
		#monofontbg = ImageFont.load_default()
		imgFont = ImageFont.truetype('Droid-Sans-Mono.ttf', 14)
		gradFont = ImageFont.truetype('Droid-Sans-Mono.ttf', 20)
		bigimgFont = ImageFont.truetype('Droid-Sans-Mono.ttf', 42)
				
		bigimg = Image.new('RGB', dimentions)
		origin = (dimentions[0]/2, dimentions[0]/2) #middle of the image		
		for e in entries:#pas:
			img = self.getImg(e, imgfilter, this_opt)
			imcl = img.convert('RGBA')
			#f = ImageFont.load_default()

			d = ImageDraw.Draw(imcl)
			d.text( (0, 0), u'{0} ({1}, {2})'.format(round(e['mean'], 2), round(e['az'], 1), round(e['el'], 1)), font=imgFont, fill='#00ff00')
			#imcl.show()
	
			#rotation = 0
			#if p['el'] != 90:
				#rotation = -(p['az']-90)
			info = self.get("positions", "glow", {"lt":e['lt']})[0]
			rotation = -(info['az']-90)
			imcl = imcl.rotate(rotation, expand = 1)
			#imcl.show()
			w,h = imcl.size
			#distance from the origin is related to the elevation
			distance = (90-info['el'])*22
			#imcl.show()
			#this code will get the distance from the origin...
			# the "- x/2" part is adjusting for the center of imcl,
			nx = int(origin[0] + math.cos(info['az']*math.pi/180)*distance - w/2)
			ny = int(origin[1] + math.sin(info['az']*math.pi/180)*distance - h/2)
			bigimg.paste(imcl, (nx,ny), imcl) #it expects integers...
		
		d = ImageDraw.Draw(bigimg)
		start = dbtime.dbtime(entries[0]['lt'])
		end = dbtime.dbtime(e['lt'])
		timestr = start.strftime("%Y-%m-%d")+" ("+start.strftime("%H:%M:%S")+" - "+end.strftime("%H:%M:%S")+")"
		 #get an aproximate size
		legend = [timestr]
		for x in ['mean', 'std', 'min', 'max']:
			val = round(opt.get(x, 0), 3)
			if val == 0:
				val = "N/A"
			legend += ["%s: %s"%(x, val)]
			
		fontH = bigimgFont.getsize("0")[1]	
		for i,e in enumerate(legend):
			d.text((140, 10+((fontH+10)*i)), e, font=bigimgFont, fill='#00ff00')
		#d.text((120, 40), "Mean: %s"%(opt['mean']), font=bigimgFont, fill='#00ff00')
		
		#display the gradient if there a uniform scale applied...
		if opt.has_key('mean') and opt.has_key('std'):
			thresh = opt.get('thresh', 5)
			buff = opt['std']*thresh
			tmax = opt['mean']+buff
			tmin = opt['mean']-buff
			grad = self.makeGradient(40, 600, opt['mean'], opt['std'], tmin, tmax, font=gradFont)
			bigimg.paste(grad, (10,10))
		#bimnm = 'nightscaled-collage-{1}{2:0>2}{3:0>2}-{4:0>2}{5:0>2}{6:0>2}-{0:0>3}.png'.format(p['passid'], p['date_year'], p['date_month'], p['date_day'], p['date_hours'], p['date_minutes'], p['date_seconds'])
		#sys.stdout.flush()

		bigimg.save(path)

	def makeGradient(self, width=20, height=400, tmean=4, tstd=.5, tmin=0, tmax=10, font=None):
		use = np.array(range(255,0,-1), dtype='uint8')
		use.shape = (255,1)
		
		if not font:
			font = ImageFont.load_default()
		
		fontW, fontH = font.getsize("000.00")
		ret = Image.new('RGBA', (width+fontW,height))
		im = Image.fromarray(np.array(use, dtype='uint8'))
		im = im.resize((width, height))
		ret.paste(im, (0,0))
		draw = ImageDraw.Draw(ret)
		color = (0,255,0)
		draw.rectangle((0,0)+(width,height-1), outline=(128,128,128))
		draw.line((0, 0)+(width+4, 0), fill=color)
		draw.text((width+10, 0), u'{0}'.format(round(tmax, 2)), font=font, fill=color)
		draw.line((0, height-1)+(width+4, height-1), fill=color)
		draw.text((width+10, height-fontH), u'{0}'.format(round(tmin, 2)), font=font, fill=color)
		factor = float(height)/(float(tmax)-float(tmin))
		meanloc = height-(float(tmean)-float(tmin))*factor
		stdval = float(tstd)*factor
		draw.line((width-4, meanloc)+(width+4, meanloc), fill=color)
		draw.text((width+10, meanloc-(fontH/2)), u'{0}'.format(round(tmean, 2)), font=font, fill=color)
		draw.line((width-2, meanloc+stdval)+(width+2, meanloc+stdval), fill=color)
		draw.line((width-2, meanloc-stdval)+(width+2, meanloc-stdval), fill=color)
		del draw
		#ret.show()
		return ret
		#im.save(sys.stdout, "PNG")

	def makeVid(self, imgdir, viddir = ''):
		if viddir == '':
			viddir = imgdir
		if not op.isdir(imgdir):
			raise RuntimeError('createposnvideos: imgdir dne: ', imgdir)
		if not op.isdir(viddir):
			os.makedirs(viddir)
		imgsglb = op.join(imgdir, '*.png')
		imgpths = glob.glob(imgsglb)
		if len(imgpths) == 0:
			raise RuntimeError('createposnvideos: no files in imgdir')
		imgpths.sort()
		imgbnm = op.basename(imgpths[0])
		imgprf = imgbnm[:16]

		cmnd = r'/usr/bin/mencoder'
		mfarg = r'mf://' + imgsglb
		fparg0 = '-mf'
		fparg1 = 'fps=10'
		otarg0 = '-o'
		otarg1 = op.join(viddir, imgprf + '-200kbs.avi')
		enarg0 = '-ovc'
		enarg1 = 'lavc'
		enarg2 = '-lavcopts'
		enarg3 = 'vcodec=msmpeg4v2:vbitrate=200'

		print('cmnd mfarg fparg otarg enarg = ')
		print(cmnd, mfarg, fparg0, fparg1, otarg0, otarg1, enarg0, enarg1, enarg2, enarg3)
		sys.stdout.flush()

		try:
			subprocess.check_call([cmnd, mfarg, fparg0, fparg1, otarg0, otarg1, enarg0, enarg1, enarg2, enarg3])
		except subprocess.CalledProcessError:
			print('FAILURE')
			print('createposnvideos: CalledProcessError on azel: ', azel)
		else:
			print('SUCCESS')
		return self #allows for chaining

	def writeLatex(self):
		basename = op.join(self.rootdir, "dataproducts", "20100308")
		climagesdir = op.join(basename, "images", "regular")
		clcatlogdir = op.join(basename, "documents")
		if not op.isdir(clcatlogdir):
			  os.makedirs(clcatlogdir)
		tex = \
"""% build a pdf like this:
% $ pdflatex file.tex
\\documentclass[letterpaper,12pt]{article}
%\\usepackage[top=1in, bottom=1in, left=1in, right=1in]{geometry} 
\\usepackage{fullpage}
\\usepackage{float}
\\usepackage{graphicx}
\\newfloat{program}{thp}{lop}
\\floatname{program}{Program}
\\setcounter{section}{0}

\\DeclareGraphicsExtensions{.png}
"""

		#datestr = '{0}-{1:0>2}-{2:0>2}'.format(cat[0]['date_year'], cat[0]['date_month'], cat[0]['date_day'])
		datestr = "2010"

		tex += u'\\title{SHAPS Collages Catalog ' + datestr + u'}\n'

		tex += \
"""
\\author{Jason Addison\\\\
\\small Textron Systems Corporation, Maui\\\\
\\small \\texttt{jaddison@systems.textron.com}\\\\
}
"""

		#tex += u'\\date{' + datetime.date.today().strftime('%B %d, %Y') + u'}\n'

		tex += u'\\begin{document}\n'
		tex += u'\\maketitle\n'
		tex += u'\\pagebreak\n'
		tex += u'\n'
		tex += u'\n'
		tex += u'\\pagestyle{myheadings}\n'
		tex += u'\\markright{Textron Systems Corporation, Maui, 2010\\hfill}\n'
		tex += u'\n'
		tex += u'\\setcounter{section}{-1}\n'

		colflnms = glob.glob(op.join(climagesdir, '*.png'))

		for fn in colflnms:
			tex += u'\\begin{figure}[!b]\n'
			tex += u'\\begin{center}\n'
			tex += u'\\includegraphics[width=7in]{../../images/collage/' + op.basename(fn) + u'}\n'
			tex += u'\\end{center}\n'
			tex += u'\\end{figure}\n'
			tex += u'\\pagebreak\n'
			tex += u'\\clearpage\n'

		tex += u'\\end{document}\n'

		#datestr2 = '{0}{1:0>2}{2:0>2}'.format(cat[0]['date_year'], cat[0]['date_month'], cat[0]['date_day'])
		datestr2 = datestr

		with open(op.join(clcatlogdir, 'catalog-collage-' + datestr2 + '.tex'), 'w') as outfile:
			outfile.write(tex)


	#Various scaling algorithms used by getImg()
	'''def imgScaleNormally(self, dtfl, opt):
		tmin = opt['mean']-opt['std']*opt['sigma']
		tmax = opt['mean']+opt['std']*opt['sigma']
		return self.imgScale(dtfl, tmin, tmax) 
	'''
	
	def imgScale(self, dtfl, tmin, tmax):
		dtfl = np.clip(dtfl,tmin,tmax)
		dtfl = dtfl - tmin
		dvsor = (tmax - tmin)
		return (dtfl / dvsor) * 255
		
	def imgRegular(self, dtfl, opt):
		#dtfl = np.clip(dtfl,opt['mean']-opt['std']*opt['sigma'],opt['mean']+opt['std']*opt['sigma'])
		#return self.imgScale(dtfl, tmin, tmax)
		return dtfl
	
	def imgNostar(self, dtfl, opt):
		return medianfilt2(dtfl, 9)
	
	#this one gets rid of the spikes...
	#this one left a few artifacts from the removal, so i dont think its an ideal solution...
	def imgSpikeless(self, dtfl, opt):
		'''
		spikeless = dtfl
		factor = 3
		for c,y in enumerate(spikeless):
			for i,e in enumerate(y):
				if e > tmean+tstd*factor or e < tmean-tstd*factor:
					spikeless[c][i] = tmean
				
					#print i, e
		'''
	
	#this is my attempt at using the histogram data to clear up inconsistencies...
	def imgHisto(self, dtfl, opt):
		#this also works...	
		(n, bins) = np.histogram(dtfl, bins=100)
		
		if opt.get('graph'):
			fig = plt.figure()
			ax = fig.add_subplot(111)
			ax.plot(.5*(bins[1:]+bins[:-1]), n)
			plt.show()			
		
		tmin = 0
		tmax = 0
		findmin = True
		for i,e in enumerate(bins):
			if n[i] > 5:
				findmin = False
			if n[i] <= 5:
				if findmin:			
					tmin = i
				else:
					tmax = i
					break
		print "min:", bins[tmin], "max:", bins[tmax]
		return np.clip(dtfl,bins[tmin],bins[tmax])

##END OF CLASS##

#might try to break up the db and the dp...
class DP(DB):
	def __init__(self, rootdir=None, debug=False):
		DB.__init__(self, rootdir, debug)
		print self

	


#i'm leaving these out of the class because they don't really need to make use of any member variables,
#so i figured they don't need to exsist in every instance of the DB class...



#used for creating the "nostar" images in the writeimage() function
def pad(orgarr, newshp, padval=0, center=False):

  # returns a list of all indecies in an array with shape, shp, as lists
  def genidx(shp):
	 if len(shp) == 1:
	   return [[x] for x in range(shp[0])]
	 else:
	   return [[n] + x for x in genidx(shp[1:]) for n in range(shp[0])]

  # list of lists to list of tuples
  def ll2lt(ll):
	 return [tuple(x) for x in ll]

  # the original array
  orgtyp = orgarr.dtype
  orgshp = orgarr.shape
  orgdim = len(orgshp)
  # the new, result, array
  newdim = len(newshp)
  newarr = np.zeros(newshp, orgtyp)
  # the mask array
  mskshp = newshp
  mskdim = newdim
  mskarr = np.ones(mskshp, dtype=np.bool)
  # intersection of original and new shapes
  minshp = filter(lambda x: x != None, map(min, orgshp, newshp)) # a py array
  mindim = len(minshp)
  # clear the mask where original values will go
  for idx in genidx(minshp):
	 # pad index if needed
	 adjidx = [0] * mskdim
	 adjidx[-mindim:] = idx
	 # clear mask
	 mskarr[tuple(adjidx)] = False
  # replace 0's in new array with pad value where mask is True
  for idx in ll2lt(genidx(mskshp)):
	 if mskarr[idx] == True:
	   newarr[idx] = padval
  # copy the original data into the new array
  for idx in genidx(minshp):
	 # pad index if needed
	 oadidx = [0] * orgdim
	 oadidx[-mindim:] = idx
	 nadidx = [0] * newdim
	 nadidx[-mindim:] = idx
	 newarr[tuple(nadidx)] = orgarr[tuple(oadidx)]

  if center:
	 # index of new origin of original data
	 newidx = [0] * newdim
	 # extended minimum shape, shape of minimum array padded for new dimensions
	 # pad with 1's for following calculation, (shape not index)
	 emishp = [1] * newdim
	 emishp[-mindim:] = minshp
	 # newidx = (newshp - minshp) / 2
	 newidx = map(lambda x: reduce(lambda y, z: (y - z) / 2, x), zip(newshp, emishp))
	 # if the new origin is the same as old, [0,0,...], skip
	 if reduce(lambda x, y: x + y, newidx) != 0:
	   idxlst = genidx(minshp)
	   idxlst.reverse()
	   for idx in idxlst:
	     frmidx = [0] * newdim
	     frmidx[-mindim:] = idx
	     # zip with plus
	     tooidx = map(lambda x: reduce(lambda y, z: y + z, x), zip(frmidx, newidx))
	     newarr[tuple(tooidx)] = newarr[tuple(frmidx)]
	     newarr[tuple(frmidx)] = padval

  return newarr

#used for creating the "nostar" images in the writeimage() function
def medianfilt2(imgin, ksize):
	 M, N = imgin.shape
	 ksz = int(ksize)
	 lkrad = ksz / 2
	 rkrad = ksz - lkrad

	 imgmed = np.median(imgin)

	 Mp = M + ksz - 1
	 Np = N + ksz - 1
	 
#     print('M = ', M)
#     print('N = ', N)
#     print('Mp = ', Mp)
#     print('Np = ', Np)
#     print('ksz = ', ksz)
#     print('lkrad = ', lkrad)
#     print('rkrad = ', rkrad)
#     print('imgmed = ', imgmed)

	 imgpad = pad(imgin, (Mp, Np), padval=imgmed, center=True)

#     print('imgpad[:10, :10] = ', imgpad[:10, :10])

	 imgout = np.zeros_like(imgin)

	 for i in xrange(lkrad, Mp - rkrad + 1):
	     for j in xrange(lkrad, Np - rkrad + 1):
	         slc = imgin[i-lkrad:i+rkrad, j-lkrad:j+rkrad].ravel()
	         imgout[i-lkrad, j-lkrad] = np.median(slc)
	         
	 return imgout
