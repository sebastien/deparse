#!/usr/bin/env python3
# encoding=utf8 ---------------------------------------------------------------
# Project           : deparse
# -----------------------------------------------------------------------------
# Author            : FFunction
# License           : BSD License
# -----------------------------------------------------------------------------
# Creation date     : 2016-11-25
# Last modification : 2019-02-14
# -----------------------------------------------------------------------------

import sys, os, argparse, fnmatch
from .core import logging, Tracker, Resolver, find, PARSERS

def run( args, recursive=False, mode=Tracker ):
	"""Extracts the dependencies of the given files."""
	if isinstance(args, str): args = [args]
	if mode == Tracker:
		tracker = Tracker()
		res  = None
		for _ in args:
			r = (tracker.fromPath(_, recursive=recursive))
			if not res:
				res = r
			else:
				res.update(r)
		return res
	elif mode == Resolver:
		res = find(args)
		return res

def process( text, path=None, recursive=True ):
	tracker = Tracker()
	tracker.fromText(text, path=path, recursive=recursive)
	return tracker

def command( args, name=None ):
	"""The command-line interface of this module."""
	if type(args) not in (type([]), type(())): args = [args]
	oparser = argparse.ArgumentParser(
		prog        = name or os.path.basename(__file__.split(".")[0]),
		description = "Lists dependencies from PAML and Sugar files"
	)
	# TODO: Rework command lines arguments, we want something that follows
	# common usage patterns.
	oparser.add_argument("files", metavar="FILE", type=str, nargs='+',
			help='The files to extract dependencies from')
	oparser.add_argument("-o", "--output",    type=str,  dest="output", default="-",
			help="Specifies an output file")
	oparser.add_argument("-t", "--type",      type=str,  dest="types",  nargs="+", default=("*",),
			help="The types to be matched, wildcards accepted")
	oparser.add_argument("-r", "--recursive", dest="recursive",  action="store_true", default=False,
			help="Recurse through the dependencies")
	oparser.add_argument("-p", "--path",      dest="show_path",  action="store_true", default=False,
			help="Shows the relative path of the element")
	oparser.add_argument("-P", "--abspath",   dest="abs_path",   action="store_true", default=False,
			help="Shows the absolute path of the element")
	oparser.add_argument("-l", "--list",      dest="list",    action="store_true", default=False,
			help="Lists the dependencies of the given symbols (find mode)")
	oparser.add_argument("-f", "--find",      dest="find",    action="store_true", default=False,
			help="Finds the files corresponding to the given symbols (find mode)")
	oparser.add_argument("-s", "--separator",      dest="sep",    action="store", default="\t",
			help="Sets the field separator in output")
	# We create the parse and register the options
	args     = oparser.parse_args(args=args)
	out      = sys.stdout
	cwd      = os.getcwd()
	# === RESOLVER ============================================================
	# This runs like a first pass, as the resolved elements might be fed
	# to the dependency tracking, for instance:
	#
	# deparse -fl module
	# deparse -fr module
	#
	if args.find:
		# We're in resolution mode, so we're trying to locate the given elements
		res   = run(args.files, recursive=args.recursive, mode=Resolver)
		paths = []
		for name in args.files:
			resolved = sorted(set(res.get(name) or ()))
			groups = {}
			for t, path in resolved:
				groups.setdefault(path,[])
				groups[path].append(t)
			if not resolved:
				logging.error("find:Could not resolve: `{0}`".format(name))
			for path in sorted(groups.keys()):
				if args.show_path or args.abs_path:
					if path not in paths:
						if args.abs_path:
							out.write(os.path.abspath(path))
						else:
							out.write(os.path.relpath(path,cwd))
						out.write("\n")
				elif not args.list or not args.recursive:
					out.write(name)
					out.write(args.sep)
					out.write(path)
					out.write(args.sep)
					out.write(",".join(groups.get(path)))
					out.write(args.sep)
				paths.append(path)
		if args.list or args.recursive:
			args.files = paths
	# === TRACKER =============================================================
	elif args.recursive or args.list:
		res = run(args.files, recursive=args.recursive, mode=Tracker)
		if not res:
			logging.error("Command returned empty result")
		elif "requires" not in res:
			logging.warn("Arguments do not seem to require anything")
		else:
			# We're in dependency mode, so we list the dependencies referenced
			# in the files given as arguments.
			resolved = []
			for item in res["requires"]:
				t, n = item
				for tp in args.types:
					if fnmatch.fnmatch(t, tp):
						if args.show_path or args.abs_path:
							# FIXME: For some reason the files are not
							# always resolved there, so we add them.
							r = set(res["resolved"].get(item) or ())
							# TODO: We might want an option to check for URLs
							item_path = item[1]
							if not r and "://" not in item_path:
								logging.error("track:Item {0} unresolved".format(item))
							for t,p in r:
								if p not in resolved:
									resolved.append(p)
									out.write(p if args.abs_path else os.path.relpath(p, cwd))
									out.write("\n")
						else:
							if n not in resolved:
								resolved.append(n)
								out.write(t)
								out.write("\t")
								out.write(n)
								out.write("\n")

# -----------------------------------------------------------------------------
#
# MAIN
#
# -----------------------------------------------------------------------------

if __name__ == "__main__":
	import sys
	command(sys.argv[1:])

# EOF - vim: ts=4 sw=4 noet
