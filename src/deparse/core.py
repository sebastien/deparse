# encoding=utf8 ---------------------------------------------------------------
# Project           : deparse
# -----------------------------------------------------------------------------
# Author            : FFunction
# License           : BSD License
# -----------------------------------------------------------------------------
# Creation date     : 2016-11-25
# Last modification : 2016-12-21
# -----------------------------------------------------------------------------

from __future__ import print_function

import sys, os, re, glob, argparse, fnmatch
from   functools import reduce

# TODO: We should introduce a high-level tracker/resolver (maybe as
# catalogue) that does caching. It should basically maintain
# a mapping of the graph:
#
# - (type,name) → path
# - path + provides  → [ (type,name) ]
# - path + requires  → [ (type,name) ]
#
# - find(name|(type,name))
# - depends|requires(path|name|item)
# - provides(path|item)

try:
	import reporter
	logging = reporter.bind("deparse", template=reporter.TEMPLATE_COMMAND)
except ImportError as e:
	import logging

if sys.version_info.major >= 3:
	unicode = str

__doc__ = """
*deparse* extracts/lists and resolves dependencies from a variety of files.
Tracker are listed as couples `(<type>, <name>)` where type is a string like
`<language>:<type>`, for instance `js:file`, `js:module`, etc.

The `deparse` module features both an API and a command-line interface.
"""

class LineParser(object):
	"""An abstract line-based parser. It looks for lines matching the
	regular expressions defined the `LINES` map and executes the corresponding
	method of the subclass with `(line, match)` as arguments.

	The `LineParser.PATH` map defines paths where specific item types
	are expected to be found. You can configure these at runtime so that
	the items can be properly resolved by the `resolve` method.
	"""

	LINES   = {}
	OPTIONS = {}
	PATHS   = {
		"js:module"   : ["lib/js"  , "src/js"  , ""],
		"js:gmodule"  : ["lib/js"  , "src/js"  , ""],
		"sjs:module"  : ["lib/sjs" , "src/sjs" , ""],
		"sjs:gmodule" : ["lib/sjs" , "src/sjs" , ""],
		"css:module"  : ["lib/css" , "src/css" , ""],
		"pcss:module" : ["lib/pcss", "src/pcss", ""],
	}

	def __init__( self ):
		self.path     = None
		self.type     = None
		self.provides = []
		self.requires = []

	def parsePath( self, path, type=None ):
		self.path = path
		self.type = type
		if not os.path.exists(path):
			logging.error("{1} parser cannot parse path {0} because it does not exist.".format(path, self.__class__.__name__))
		else:
			with open(path) as f:
				self.onParse(path, type)
				for line in f.readlines():
					self.parseLine(line)
				self.onParseEnd(path, type)
		self.path = None
		self.type = None
		return self

	def parseText( self, text, path=None, type=None ):
		return self.parse(text, path=path, type=type)

	def parse( self, text, path=None, type=None ):
		self.onParse(path or self.path, type)
		for line in text.split("\n"):
			self.parseLine(line)
		return self

	def normpath( self, path ):
		"""Returns the normalized path, where if the path is relative, it is considered
		relative to the currenlty parsed path, otherwise it will be returned as absolute."""
		if os.path.abspath(path) == path: return path
		return os.path.normpath(os.path.join(os.path.dirname(self.path), path)) if self.path else os.path.normpath(path)

	def parseLine( self, line ):
		for name, expr in self.LINES.items():
			match = re.match(expr, line)
			if match:
				getattr(self, name)(line, match)
				break
		return self

	def onParse( self, path, type ):
		pass

	def onParseEnd( self, path, type ):
		pass

	# FIXME: From an architecture standpoint, this should be pluggable.
	def resolve( self, item, path, dirs=(), verbose=False ):
		"""Finds the actual path for the given item `(type, name)`, returning
		a list of the matching paths (the item might be implemented by more than
		one file)."""
		cwd     = os.path.abspath(".")
		t, name = item
		res     = []
		dirs    = [_ for _ in dirs] + [os.getcwd(), os.path.dirname(os.path.abspath(path)) if not os.path.isdir(path) else os.path.abspath(path)]
		# TODO: Support resolvers
		if not t or t in ("js:module", "sjs:module"):
			name = name.replace(".", "/")
			all_dirs = self._subdirs(dirs, *self.PATHS["js:module"])
			js_modules  = sorted([("js:module", _) for _ in self._glob(all_dirs, "{0}-*.js".format(name,)) if ".gmodule" not in _])
			all_dirs = self._subdirs(dirs, *self.PATHS["sjs:module"])
			sjs_modules = sorted([("sjs:module", _) for _ in self._glob(all_dirs, "{0}.sjs".format(name ),  "{0}*-*.sjs".format(name))])
			res += sjs_modules if sjs_modules else (js_modules[-1],) if js_modules else ()
		if not t or t in ("js:gmodule", "sjs:gmodule"):
			name = name.replace(".", "/")
			all_dirs = self._subdirs(dirs, *self.PATHS["js:module"])
			js_modules  = sorted([("js:gmodule", _) for _ in self._glob(all_dirs, "{0}-*.js".format(name)) if ".gmodule" in _])
			all_dirs = self._subdirs(dirs, *self.PATHS["sjs:module"])
			sjs_modules = sorted([("sjs:gmodule", _) for _ in self._glob(all_dirs, "{0}*.sjs".format(name), "{0}*-*.sjs".format(name))])
			res += sjs_modules if sjs_modules else (js_modules[-1],) if js_modules else ()
		if t and t in ("js:component", "sjs:component"):
			res += Component.Resolve(item, path ,dirs)
		if not t or t in ("css:module" ,"pcss:module"):
			all_dirs = [cwd] + self._subdirs(dirs, *self.PATHS["css:module"])
			css_modules  = sorted([("css:module",  _) for _ in self._glob(all_dirs, "{0}.css".format(name))])
			all_dirs = [cwd] + self._subdirs(dirs, *self.PATHS["pcss:module"])
			pcss_modules = sorted([("pcss:module", _) for _ in self._glob(all_dirs, "{0}*.pcss".format(name))])
			res += pcss_modules if pcss_modules else (css_modules[-1],) if css_modules else ()
		if not t or t.endswith(":file"):
			altname = name + ("." + t.split(":",1)[0] if t else "")
			ext     = name.rsplit(".", 1)[-1]
			visited = []
			for n in (name, altname, "lib/" + ext + "/" + name, "lib/" + ext + "/", altname):
				for d in dirs:
					p = os.path.join(d, n)
					if p not in visited and os.path.exists(p):
						res.append(("*:file", p))
						visited.append(p)
		if t and t.endswith(":url"):
			res.append(item)
		res = self._resolve( res, item, path, dirs=() )
		if verbose and not res:
			logging.error("Unresolved item in {0}: {1} at {2}".format(self.__class__.__name__, item, path))
		res = reduce(lambda x,y:x + [y] if y not in x else x, res, [])
		return res

	def _resolve( self, resolved, item, path, dirs ):
		"""Can be overriden to update the result of `resolve`."""
		return resolved

	def _subdirs( self, dirs, *subdirs):
		"""Returns `len(dirs) * len(subdirs)` directories where each `subdir` is joined
		with all the `dirs`."""
		res = []
		for sd in subdirs:
			res += [os.path.join(d,sd) for d in dirs]
		res += dirs
		return res

	def _glob( self, dirs, *expressions ):
		matches = []
		for d in dirs:
			for e in expressions:
				p = os.path.join(d, e)
				matches += glob.glob(p)
		return sorted(matches)

	def export( self ):
		return dict(
			path=self.path,
			provides=self.provides,
			requires=self.requires,
		)

# -----------------------------------------------------------------------------
#
# C PARSER
#
# -----------------------------------------------------------------------------

class C(LineParser):
	"""Dependency parser for C files."""

	LINES = {
		"onInclude"  : "^\s*#include\s+[<\"]([^\>\"]+)[>\"]",
	}

	def onParse( self, path, type ):
		module = os.path.basename(path).rsplit("-",1)[0]
		self.provides = [("c:header", module)]

	def onInclude( self, line, match ):
		self.requires.append(("c:header",match.group(1)))

# -----------------------------------------------------------------------------
#
# JAVASCRIPT PARSER
#
# -----------------------------------------------------------------------------

class JavaScript(LineParser):
	"""Dependency parser for JavaScript files."""

	# SEE: https://github.com/google/closure-library/wiki/goog.module:-an-ES6-module-like-alternative-to-goog.provide
	LINES = {
		"onRequire"       : "(var\s+|exports\.)([\w\d_]+)\s*=\s*require\s*\(([^\)]+)\)(\.([\w\d_]+))?(\.([\w\d_]+))?\s*;?",
		"onImport"        : "\s*import\s+({[^}]*}|\*(\s+as\s+[_\-\w]+)|[_\-\w]+)\s*(from\s+['\"]([^'\"]+)['\"])?",
		"onGoogleProvide" : "goog\.(provide|module)\s*\(['\"](^['\"]+)['\"]\)",
		"onGoogleRequire" : "goog\.require\s*\(['\"](^['\"]+)['\"]\)",
	}

	def onParse( self, path, type ):
		if path:
			module  = os.path.basename(path).rsplit("-",1)[0]
			self.provides = [(self.type or "js:module", module)]
		else:
			self.provdes = []

	def onRequire( self, line, match ):
		decl, name, module, __, symbol, __, subsymbol = match.groups()
		self.requires.append((self.type or "js:module", module))

	def onGoogleProvide( self, line, match ):
		self.provides.append(("js:gmodule", match.group(1)))

	def onGoogleRequire( self, line, match ):
		self.requires.append(("js:gmodule", match.group(1)))

	def onImport( self, line, match ):
		module = match.groups()[-1]
		if not module:
			return
		if module.startswith("."):
			path = os.path.normpath(os.path.join(os.path.dirname(self.path or "."), module))
			self.requires.append(("js:file", path))
		else:
			self.requires.append((self.type or "js:module", module))

# -----------------------------------------------------------------------------
#
# SUGAR PARSER
#
# -----------------------------------------------------------------------------

class Sugar(LineParser):
	"""Dependency parser for Sugar files."""

	OPTIONS = {
	}

	LINES = {
		"onModule"  : "^@module\s+([^\s]+)",
		"onSugar2"  : "^@feature\s+sugar\s*[= ]\s*2.*$",
		"onImport"  : "^@import",
	}

	def __init__( self, version=1 ):
		super(Sugar, self).__init__()
		self.version = version

	def onParse( self, path, type=None ):
		self.requires = []
		self.version  = 1

	def onParseEnd( self, path, type=None ):
		pass
		# if self.version == 1:
		# 	self.requires.insert(0, (self.type or "js:module", "extend"))

	def onModule( self, line, match ):
		self.provides.append((self.type or "js:module",match.group(1)))

	def onSugar2( self, line, match ):
		self.version = 2

	def onImport( self, line, match ):
		line = line[len(match.group()):]
		if " from " in line: line = line.split(" from ", 1)[1]
		for _ in line.split(","):
			_ = _.strip().split()[0]
			if _:
				self.requires.append((self.type or "js:module",_))

# -----------------------------------------------------------------------------
#
# PAML PARSER
#
# -----------------------------------------------------------------------------

class Paml(LineParser):
	"""Dependency parser for PAML files."""

	# NOTE: Borrowed from paml.engine
	SYMBOL_NAME    = "\??([\w\d_-]+::)?[\w\d_-]+"
	SYMBOL_ATTR    = "(%s)(=('[^']+'|\"[^\"]+\"|([^),]+)))?" % (SYMBOL_NAME)
	SYMBOL_ATTRS   = "^%s(,%s)*$" % (SYMBOL_ATTR, SYMBOL_ATTR)
	RE_ATTRIBUTE   = re.compile(SYMBOL_ATTR)
	RE_SCRIPT      = re.compile("(\t)*<script([^:\n]*)")

	LINES = {
		"onLinkTag"           : "^\t+<link\(",
		"onJavaScriptTag"     : "^\t+<script\(",
		"onJavaScriptRequire" : "^\t+@(import|require)\:js\(",
		"onJavaScriptGModule" : "^\t+@(import|require)\:gmodule\(",
		"onCSSRequire"        : "^\t+@(import|require)\:css\(",
		"onComponent"         : "^\t.*[,(]data-component=([^,)]+)",
		"onInclude"           : "^\t+%include\s*"
	}

	def __init__( self ):
		super(Paml, self).__init__()
		self.subparser = None
		self.subparserIndent = 0

	def _getIndentation( self, line ):
		i = 0
		while i < len(line) and line[i] == "\t": i += 1
		return i

	def parseLine(self, line ):
		# Paml can contain embedded languages, so we make sure
		# we support them here.
		script = self.RE_SCRIPT.match(line)
		if self.subparser:
			indent = self._getIndentation(line)
			if indent > self.subparserIndent:
				self.subparser.parseLine(line[indent:])
			else:
				self.subparser.onParseEnd(self.path, self.type)
				self.subparser = None
		if script:
			if self.subparser:
				self.subparser.onParseEnd(self.path, self.type)
			indent = len(script.group(1) or "")
			lang   = script.group(2).split("@")[-1]
			if lang == "sugar":
				self.subparser = Sugar()
			else:
				self.subparser = JavaScript()
			self.subparser.onParse(self.path, self.type)
			# We bind the provides/requires
			self.subparser.provides = self.provides
			self.subparser.requires = self.requires
			self.subparserIndent = indent
		return super(Paml, self).parseLine(line)

	def _parseAttributes( self, attributes ):
		# NOTE: Borrowed and adapted from paml.engine.Parser._parsePAMLAttributes
		result   = []
		original = attributes
		while attributes:
			match  = self.RE_ATTRIBUTE.match(attributes)
			assert match, "Given attributes are malformed: %s" % (attributes)
			name  = match.group(1)
			value = match.group(4)
			# handles '::' syntax for namespaces
			name = name.replace("::",":")
			if value and value[0] == value[-1] and value[0] in ("'", '"'):
				value = value[1:-1]
			result.append([name, value])
			attributes = attributes[match.end():]
			if attributes:
				assert attributes[0] == ",", "Attributes must be comma-separated: %s" % (attributes)
				attributes = attributes[1:]
				assert attributes, "Trailing comma with no remaining attributes: %s" % (original)
		return dict((k,v) for k,v in result)

	def onLinkTag( self, line, match ):
		attrs = self._parseAttributes(line.split('(', 1)[-1].rsplit(")",1)[0])
		url = attrs.get("href")
		if attrs.get("rel") == "stylesheet" and url:
			if "://" in url:
				self.requires.append(("css:url",  url))
			else:
				self.requires.append(("css:file", url))

	def onJavaScriptTag( self, line, match ):
		src = line.split("src=",1)[1].split(",")[0].split(")")[0]
		if src[0] == src[-1] and src[0] in '"\'': src = src[1:-1]
		self.requires.append(("js:file", src))

	def onJavaScriptRequire( self, line, match, type="js:module"):
		reqs = line.split("(",1)[1].rsplit(")",1)[0].split(",")
		for name in reqs:
			self.requires.append((type, name))

	def onJavaScriptGModule( self, line, match ):
		return self.onJavaScriptRequire(line, match, type="js:gmodule")

	def onCSSRequire( self, line, match ):
		return self.onJavaScriptRequire(line, match, type="css:module")

	def onComponent( self, line, match ):
		component = match.group(1).strip()
		if component[0] == component[-1] and component[-1] in "'\"":
			component = component[1:-1]
		self.requires.append(("js:component", component))

	def onInclude( self, line, match ):
		line = line[len(match.group()):]
		line = line.split("+",1)[0].split("{",1)[0].strip()
		if not os.path.splitext(line)[-1]: line += ".paml"
		type = "paml:file"
		if line.endswith(".svg"):
			type = "*:file"
		self.requires.append((type, line))

# -----------------------------------------------------------------------------
#
# CSS PARSER
#
# -----------------------------------------------------------------------------

class CSS(LineParser):
	"""Dependency parser for (P)CSS files."""

	OPTIONS = {}

	LINES = {
		"onImport"  : "^@import\s+(.+)",
		"onURL"     : "^.*url\(([^\)]+)\)"
	}

	def onImport( self, line, match ):
		path = match.group(1).strip()
		if path[0] == path[-1] and path[0] in '"\'': path = path[1:-1]
		self.requires.append(("css:file", self.normpath(path)))

	def onURL( self, line, match ):
		url = match.group(1)
		if url[0] == url[-1] and url[0] in "\"'": url = url[1:-1]
		if url.startswith("file://"): url = url[7:]
		self.requires.append(("*", url if "://" in url else self.normpath(url.split("?",1)[0].split("#",1)[0])))

# -----------------------------------------------------------------------------
#
# PCSS PARSER
#
# -----------------------------------------------------------------------------

class PCSS(CSS):
	"""Dependency parser for PCSS files."""

	OPTIONS = {}

	LINES = {
		"onModule"  : "^@module\s+([^\s]+)",
		"onInclude" : "^@include\s+([^\s]+)",
		"onImport"  : "^@import\s+(.+)",
		"onURL"     : "^.*url\(([^\)]+)\)"
	}

	def onModule( self, line, match ):
		self.provides.append(("pcss:module",match.group(1)))

	def onInclude( self, line, match ):
		path = match.group(1).strip()
		self.requires.append(("pcss:file", self.normpath(path)))

	def onImport( self, line, match ):
		path = match.group(1).strip()
		if path[0] == path[-1] and path[0] in '"\'': path = path[1:-1]
		self.requires.append(("css:module", self.normpath(path)))

# -----------------------------------------------------------------------------
#
# BLOCK PARSER
#
# -----------------------------------------------------------------------------

class Block(LineParser):
	"""Dependency parser for .block files."""

	OPTIONS = {}

	LINES = {
		"onDirective" : "^@(\w[\w\d]*)(\s+.*)?$",
		"onContent"   : "^\t(.*)$"
	}

	def __init__( self ):
		super(Block, self).__init__()
		self.blocks   = None

	def onParse( self, path, type ):
		super(Block, self).onParse(path, type)
		self.blocks = []

	def onParseEnd( self, path, type ):
		super(Block, self).onParseEnd(path, type)
		for name, params, lines in self.blocks:
			parser = None
			if name == "sugar2":
				parser = Sugar(version=2)
			elif name == "paml":
				parser = Paml()
			elif name == "pcss":
				parser = PCSS()
			elif name == "import":
				self.requires += [("{0}:file".format(_.rsplit(".",1)[-1]), _.strip()) for _ in params.split(" ") if _.strip()]
			elif name == "component":
				self.requires += [("component", _.strip()) for _ in params.split(" ") if _.strip()]
			# TODO: Texto
			if parser:
				parser.parse("\n".join(lines), path=path)
				self.provides += parser.provides
				self.requires += parser.requires

	def onDirective( self, line, match ):
		self.blocks.append([match.group(1), match.group(2), []])

	def onContent( self, line, match ):
		if self.blocks:
			self.blocks[-1][2].append(line[1:])

# -----------------------------------------------------------------------------
#
# COMPONENT PARSER
#
# -----------------------------------------------------------------------------

class Component(LineParser):
	"""Parses component directories."""

	OPTIONS = {
		"path"  : ["components"],
		"files" : (
			("js:module",  "model.js"),
			("sjs:module", "model.sjs"),
			("js:module",  "view.js"),
			("paml:file",  "view.xml.paml"),
			("xml:file",   "view.xml"),
			("html:file",  "view.html"),
			("css:file",   "style.css"),
			("pcss:file",  "style.pcss"),
			("hjson:file", "options.hjson"),
			("json:file",  "options.json"),
		)
	}

	@classmethod
	def Resolve( cls, item, path, dirs=(), verbose=False ):
		res     = []
		dirs    = dirs or cls.OPTIONS["path"]
		paths   = [_ for _ in dirs] + [os.getcwd()]
		if path:
			paths.append(os.path.dirname(os.path.abspath(path)) if not os.path.isdir(path) else os.path.abspath(path))
		for parent in set(paths):
			for sub in cls.OPTIONS["path"]:
				d = os.path.join(os.path.join(parent, sub), item[1])
				for t,f in cls.OPTIONS["files"]:
					p = os.path.join(d, f)
					if os.path.exists(p):
						res.append((t,p))
		return res

	def __init__( self ):
		super(Component, self).__init__()

	def resolve( self, item, path, dirs=(), verbose=False ):
		return self.Resolve(item, path, dirs)

# -----------------------------------------------------------------------------
#
# DEPENDENCIES
#
# -----------------------------------------------------------------------------

class Tracker(object):
	"""Extracts and aggregates dependencies."""

	def __init__( self ):
		self.PARSERS   = PARSERS
		self.provides  = []
		self.requires  = []
		self.paths     = []
		self.resolved  = {}
		self.nodes     = {}
		self._resolver = None

	def fromPath( self, path, recursive=False ):
		"""Lists the dependencies at the given path in import priority. This
		method supports paths containing multiple files, for instance:


		```
		lib/js/jquery.js+lodash.js
		```

		will be translated to

		```
		["lib/js/jquery.js", "lib/js/lodash.js"]
		```

		if the file `lib/js/jquery.js+lodash.js` does not exists.
		"""
		self._fromPath(path, recursive=recursive)
		return {
			"provides":self.provides,
			"resolved":self.resolved,
			"requires":self._sortRequires(self.requires)
		}

	def _fromPath( self, path, recursive=False, type=None ):
		"""Helper function of the `Tracker.fromPath` method. Gets a parser
		for the given file type, parses the file at the given path and
		merges the `Parser.provides`/`Parser.requires`.
		"""
		if not os.path.exists(path) and "+" in path:
			# We're given a  '+'-separated list of paths, so we split it
			paths  = path.split("+")
			prefix = os.path.dirname(paths[0])
			paths  = [paths[0]] + [os.path.join(prefix, _) for _ in paths[1:]]
			return [self._fromPath(_, recursive=recursive, item=item) for _ in paths]
		elif path in self.paths:
			# We've already scanned that path, so we return as-is
			return self
		elif os.path.isdir(path):
			# We skip directories
			pass
		else:
			# We add the path to prevent infinite recursion
			self.paths.append(path)
			# Now we find a parser for the extension
			ext         = path.rsplit(".",1)[-1].lower()
			parser_type = self.PARSERS.get(ext)
			# We return and log an error if there's no matching parser
			if not parser_type:
				logging.error("Parser not defined for type `{0}` in: {1}".format(ext, path))
				return
			# We do the parsing, merging back the provided and required elements.
			parser      = parser_type().parsePath(path, type=type)
			self.provides.append((path, parser.provides))
			self.requires = self._merge(self.requires, parser.requires)
			# We register/update the provided nodes
			for name in parser.provides:
				if name not in self.nodes: self.nodes[name] = []
				self.nodes[name] = self._merge(self.nodes[name], parser.requires)
			# We iterate on the dependency, trying to resolve them
			for dependency in parser.requires:
				# We don't resolve URLs (yet)
				dependency_type = dependency[0]
				if dependency_type.endswith(":url"):
					continue
				resolved = self.resolve(parser, dependency, path)
				if recursive:
					# FIXME: Support url
					# if not resolved and "://" not in dependency[1]:
					# 	logging.error("Cannot recurse on {0} in {1}: dependency {0} cannot be resolved".format(dependency, path))
					for dependency_type, dependency_path in resolved:
						self._fromPath(dependency_path, recursive=recursive, type=dependency_type)

	# FIXME: Architecturally, this is a helper function and should be moved
	# out of the class if used elsewhere.
	def _merge( self, a, b ):
		"""Merges the elemetns of B into A, only if the elements
		are not arelady in A."""
		for e in b:
			if e not in a:
				a.append(e)
		return a

	def resolve( self, parser, item, path ):
		"""Finds the actual path for the given item `(type, name)`, returning
		a list of the matching (type, paths) (the item might be implemented by more than
		one file)."""
		# We resolve with the parser first
		res = [_ for _ in parser.resolve(item, path)] or ()
		t, name = item
		# If we haven't found anything, we use the resolver
		if not res:
			if not self._resolver:
				self._resolver = Resolver(self.PARSERS)
			r = self._resolver.find([item], path)
			if name in r:
				res = r[name]
		# NOTE: We hash on the *item* as a symbol might have more than one file
		if item not in self.resolved:
			# If the item path exists (but does not have a parser), then
			# we add it as resolved.
			self.resolved[item] = [item] if os.path.exists(item[1]) else []
		self.resolved[item] = self._merge(self.resolved[item], res)
		return res

	def _sortRequires( self, requires ):
		"""Sorts the given list of requirements so that the given list is
		returned in loading order."""
		loaded = []
		requires = sorted(requires, key=lambda _:len(self.nodes.get(_) or ()))
		def load(module, loaded=loaded):
			if module in loaded: return
			index = len(loaded)
			loaded.append(module)
			for required in self.nodes.get(module) or ():
				# NOTE: This is a bug, the modules should not import themselves
				if required == module: continue
				load(required, loaded)
			del loaded[index]
			if module not in loaded:
				loaded.append(module)
			return loaded
		for _ in requires:
			load(_)
		return loaded

# -----------------------------------------------------------------------------
#
# RESOLVER
#
# -----------------------------------------------------------------------------

class Resolver(object):
	"""Resolves (symbol) names into files."""

	def __init__( self, parsers=None ):
		super(Resolver, self).__init__()
		self.PARSERS = parsers or PARSERS
		self.paths = []

	def addPath( self, path ):
		self.paths.append(path)
		return self

	def find( self, elements, path=None ):
		parsers = [(_, self.PARSERS[_]()) for _ in self.PARSERS]
		matches = {}
		path    = path or os.getcwd()
		if isinstance(elements, str) or isinstance(elements, unicode): elements=[elements]
		for element in elements:
			if isinstance(element, tuple): element = element[1]
			for t,p in parsers:
				matches.setdefault(element,[])
				# We ensure an element is not present twice
				for _ in p.resolve((None,element), path, self.paths):
					if _ not in matches[element]:
						matches[element].append(_)
		return matches

# -----------------------------------------------------------------------------
#
# PARSERS
#
# -----------------------------------------------------------------------------

PARSERS = {
	"block"     : Block,
	"paml"      : Paml,
	"sjs"       : Sugar,
	"js"        : JavaScript,
	"pcss"      : PCSS,
	"css"       : CSS,
	"c"         : C,
	"cxx"       : C,
	"c++"       : C,
	"cpp"       : C,
	"h"         : C,
	"component" : Component
}

# -----------------------------------------------------------------------------
#
# COMMAND-LINE INTERFACE
#
# -----------------------------------------------------------------------------

def parse( path ):
	"""Tries to parse the file at the given path and return a list of
	the symbols that it provides as a couple `(type, [provides])`."""
	ext = path.rsplit(".", 1)[-1]
	parser = PARSERS.get(ext)
	if parser:
		parser = parser()
		return parser, parser.parsePath(path).export()
	else:
		return None, None

def provides( path ):
	"""Tries to parse the file at the given path and return a list of
	the symbols that it provides, if any."""
	parser, res = parse(path)
	return res["provides"] if res else ()

def find( args, recursive=True, resolve=False ):
	"""Finds/lists the dependencies declared in the given files."""
	rsl = Resolver()
	res = None
	if isinstance(args, str) or isinstance(args, unicode): args = [args]
	for _ in args:
		r = (rsl.find(_))
		if not res:
			res = r
		else:
			res.update(r)
	return res

def list( args, recursive=True, resolve=False ):
	"""Lists all the dependencies listed in the given files."""
	deps = Tracker()
	res  = {}
	if isinstance(args, str) or isinstance(args, unicode): args = [args]
	for _ in args:
		r = (deps.fromPath(_, recursive=recursive))
		if not res:
			res = r
		else:
			res.update(r)
	return res.get("requires") or ()


# EOF - vim: ts=4 sw=4 noet
