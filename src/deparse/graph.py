#!/usr/bin/env python3
# encoding=utf8 ---------------------------------------------------------------
# Project           : deparse
# -----------------------------------------------------------------------------
# Author            : FFunction
# License           : BSD License
# -----------------------------------------------------------------------------
# Creation date     : 2016-12-21
# Last modification : 2016-12-21
# -----------------------------------------------------------------------------

import sys, argparse, fnmatch
from deparse.core import Tracker

# -----------------------------------------------------------------------------
#
# GRAPHER
#
# -----------------------------------------------------------------------------

class Grapher(object):

	def __init__( self, types=None, output=sys.stdout ):
		self.types  = types
		self.output = output
		self.keys   = []

	def name( self, item ):
		if isinstance(item, tuple):
			return item[1]
		else:
			return item
		#return "".join(_ if _ in "abcdefghijklnmnopqrstuvwxyz0123456789.")

	def key( self, text ):
		if isinstance(text, tuple):
			text = "".join(str(_) for _ in text)
		try:
			res = self.keys.index(text)
		except ValueError:
			self.keys.append(text)
			res = len(self.keys) - 1
		return res

	def graph( self, tracker ):
		nodes = []
		edges = []
		self.onStart(tracker)
		for k,v in tracker.nodes.items():
			if self.matches(k):
				nodes.append(k)
				self.onNode(k)
				for e in v:
					if not self.matches(e): continue
					self.onEdge(k,e)
					edges.append((k,e))
				self.onNodeEnd(k)
		self.onEnd(tracker, nodes, edges)
		return nodes, edges

	def matches( self, item ):
		"""Tells if the given `item` matches the
		`.types` given at construction."""
		if not self.types:
			return True
		if isinstance(item,tuple): item=item[0]
		for t in self.types:
			if fnmatch.fnmatch(item, t):
				return True
		return False

	def onStart( self, tracker ):
		pass

	def onNode( self, node ):
		pass

	def onNodeEnd( self, node ):
		pass

	def onEdge( self, source, destination ):
		pass

	def onEnd( self, tracker, nodes, edges ):
		pass

	def writeln( self, *lines ):
		for line in lines:
			self.output.write(line)
			self.output.write("\n")

# -----------------------------------------------------------------------------
#
# DOT
#
# -----------------------------------------------------------------------------

class Dot(Grapher):
	"""Outputs a directed graph in DOT (graphviz) format of the tracker's
	dependency graph."""

	def onStart( self, tracker ):
		self.writeln("digraph G {")

	def _onNode( self, node ):
		self.writeln("{0}[label=\"{1}\"]".format(self.key(node), node[1]))

	def _onEdge( self, source, destination ):
		self.writeln("{0} -> {1}".format(self.key(source), self.key(destination)))

	def onEnd( self, tracker, nodes, edges ):
		[self._onNode(_) for _ in nodes]
		[self._onEdge(s,d) for s,d in edges]
		self.writeln("}")

# -----------------------------------------------------------------------------
#
# PLANTUML
#
# -----------------------------------------------------------------------------

class PlantUML(Grapher):

	def onStart( self, tracker ):
		self.writeln(
			"@startuml",
			"skinparam packageStyle rect"
		)

	def _onNode( self, node ):
		self.writeln("package {0} {{}}".format(self.name(node)))

	def _onEdge( self, source, destination ):
		self.writeln("{0} +-- {1}".format(
			self.name(source[1]),
			self.name(destination[1])
		))

	def onEnd( self, tracker, nodes, edges ):
		[self._onNode(_) for _ in nodes]
		[self._onEdge(s,d) for s,d in edges]
		self.writeln("@enduml")

# -----------------------------------------------------------------------------
#
# COMMAND
#
# -----------------------------------------------------------------------------

def command( args, name=None ):
	"""The command-line interface of this module."""
	USAGE = "{0} FILE...".format(name or os.path.basename(__file__))
	if type(args) not in (type([]), type(())): args = [args]
	oparser = argparse.ArgumentParser(
		prog        = name or os.path.basename(__file__.split(".")[0]),
		description = "Creates a graph of depencies for the given files."
	)
	oparser.add_argument("files", metavar="FILE", type=str, nargs='+',
			help='The files to extract dependencies from')
	# oparser.add_argument("-o", "--output",    type=str,  dest="output", default="-",
	#		help="Specifies an output file")
	oparser.add_argument("-t", "--type",      type=str,  dest="types",  nargs="+", default=("*",),
			help="The types to be matched, wildcards accepted")
	# oparser.add_argument("-f", "--format",    type=str,  dest="format",  nargs="+", default=("*",),
	# 		help="The types to be matched, wildcards accepted")
	args     = oparser.parse_args(args=args)
	# We parse all the dependencies
	tracker = Tracker()
	for _ in args.files: tracker.fromPath(_, recursive=True)
	grapher = PlantUML(args.types)
	grapher.graph(tracker)

# -----------------------------------------------------------------------------
#
# MAIN
#
# -----------------------------------------------------------------------------

if __name__ == "__main__":
	import sys
	command(sys.argv[1:])

# EOF - vim: ts=4 sw=4 noet
