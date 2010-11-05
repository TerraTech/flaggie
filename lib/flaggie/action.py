#!/usr/bin/python
#	vim:fileencoding=utf-8
# (C) 2010 Michał Górny <gentoo@mgorny.alt.pl>
# Released under the terms of the 3-clause BSD license.

import fnmatch

class ParserError(Exception):
	pass

class Action(object):
	class BaseAction(object):
		class Pattern(object):
			def __init__(self, s):
				self.pattern = s

			def __eq__(self, s):
				return fnmatch.fnmatchcase(s, self.pattern)

		def __init__(self, arg, key):
			self.args = set((arg,))
			self.ns = None

		def clarify(self, pkgs, cache):
			if len(self.args) > 1:
				raise AssertionError('clarify() needs to be called before actions are joined.')
			arg = self.args.pop()

			splitarg = arg.split('::', 1)
			if len(splitarg) > 1:
				arg = splitarg[1]

				if splitarg[0] == '*':
					ns = None
					# special case: ?*:: or %*::
					if not arg:
						raise NotImplementedError('*:: namespace support not implemented yet.')
				else:
					try:
						cache.describe(splitarg[0])
					except AssertionError:
						raise ParserError('incorrect namespace in arg')
					ns = set((splitarg[0],))
			else:
				ns = None

			if not arg:
				arg = '*'
			# Check whether the argument looks like a pattern
			for schr in ('*', '?', '['):
				if schr in arg:
					if not ns:
						ns = set(('use',))
					self.ns = ns.pop()
					self.args.add(self.Pattern(arg))
					return

			if not pkgs:
				wis = cache.glob_whatis(arg, restrict = ns)
				if len(wis) > 1:
					raise ParserError('Ambiguous argument: %s (matches %s).' % \
							(arg, ', '.join(wis)))
				elif wis:
					ns = wis.pop()
				elif ns:
					ns = ns.pop()
					print('Warning: %s seems to be an incorrect global %s' % \
							(arg, cache.describe(ns)))
				else:
					ns = 'use'
					print('Warning: %s seems to be an incorrect global flag' % arg)
			else:
				for p in pkgs:
					wis = cache.whatis(arg, p, restrict = ns)
					if wis:
						gwis = wis
					elif ns:
						gwis = ns
					else:
						gwis = cache.glob_whatis(arg)

					if len(gwis) > 1:
						raise ParserError('Ambiguous argument: %s (matches %s).' % \
								(arg, ', '.join(wis)))
					elif wis:
						ns = wis.pop()
					else:
						if gwis:
							ns = gwis.pop()
							print('Warning: %s seems to be an incorrect %s for %s' % \
									(arg, cache.describe(ns), p))
						else:
							ns = 'use'
							print('Warning: %s seems to be an incorrect flag for %s' % (arg, p))
			self.ns = ns
			self.args.add(arg)

		def append(self, arg):
			if isinstance(arg, self.__class__):
				self.args.update(arg.args)
			else:
				self.args.add(arg)

	class EffectiveEntryOp(BaseAction):
		def grab_effective_entry(self, p, arg, f, rw = False):
			entries = f[p]
			for pe in entries:
				flags = pe[arg]
				for f in flags:
					if rw:
						pe.modified = True
					return f
			else:
				if not rw:
					return None
				# No matching flag found. Try to append to the last
				# package entry if there's one. Otherwise, append
				# a new entry.
				for pe in f[p]:
					return pe.append(arg)
				else:
					return f.append(p).append(arg)

	class enable(EffectiveEntryOp):
		def __call__(self, pkgs, pfiles):
			for p in pkgs:
				for arg in self.args:
					f = self.grab_effective_entry(p, arg, pfiles[self.ns], rw = True)
					f.modifier = ''

	class disable(EffectiveEntryOp):
		def __call__(self, pkgs, pfiles):
			for p in pkgs:
				for arg in self.args:
					f = self.grab_effective_entry(p, arg, pfiles[self.ns], rw = True)
					f.modifier = '-'

	class reset(BaseAction):
		def __call__(self, pkgs, pfiles):
			puse = pfiles[self.ns]
			for p in pkgs:
				for pe in puse[p]:
					for f in self.args:
						del pe[f]
					if not pe:
						puse.remove(pe)

	class output(BaseAction):
		def __call__(self, pkgs, pfiles):
			puse = pfiles[self.ns]
			for p in pkgs:
				l = [p]
				flags = {}
				for pe in puse[p]:
					for arg in self.args:
						for f in pe[arg]:
							if f.name not in flags:
								flags[f.name] = f
				for arg in self.args:
					if arg not in flags and not isinstance(arg, self.Pattern):
						flags[arg] = None
				if not flags:
					return
				for fn in sorted(flags):
					l.append(flags[fn].toString() if flags[fn] is not None else '?%s' % fn)

				print(' '.join(l))

	mapping = {
		'+': enable,
		'-': disable,
		'%': reset,
		'?': output
	}
	order = (enable, disable, reset, output)

	class NotAnAction(Exception):
		pass

	def __new__(cls, *args, **kwargs):
		a = args[0]
		if a[0] in cls.mapping:
			newargs = (a[1:], a[0]) + args[1:]
			return cls.mapping[a[0]](*newargs, **kwargs)
		else:
			raise cls.NotAnAction
		
class ActionSet(list):
	def __init__(self, cache = None):
		list.__init__(self)
		self._cache = cache
		self.pkgs = []

	def append(self, item):
		if isinstance(item, Action.BaseAction):
			item.clarify(self.pkgs, self._cache)
			for a in self:
				if isinstance(item, a.__class__) and item.ns == a.ns:
					a.append(item)
					break
			else:
				list.append(self, item)
				self.sort(key = lambda x: Action.order.index(x.__class__))
		else:
			self.pkgs.append(item)

	def __call__(self, pfiles):
		if self.pkgs:
			for a in self:
				if a.ns not in pfiles:
					raise AssertionError('Unexpected ns %s in ActionSet.__call__()' % a.ns)
				a(self.pkgs, pfiles)
		else:
			raise NotImplementedError('Global actions are not supported yet')
