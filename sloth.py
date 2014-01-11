#!/usr/bin/python3

# Copyright 2014 Maximilian Stahlberg
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys, os, re, argparse, copy, configparser

from PIL import Image


class ShaderGenerator(dict):

	# valid color format
	colorRE = re.compile("^[0-9a-f]{6}$")

	# mapping from surfaceparm values to words that trigger their use when keyword guessing is enabled
	surfaceParms = \
	{
		"donotenter": ["lava", "slime"],
		"dust":       ["sand", "dust"],
		"flesh":      ["flesh", "meat", "organ"],
		"ladder":     ["ladder"],
		"lava":       ["lava"],
		"metalsteps": ["metal", "steel", "iron", "tread", "grate"],
		"slick":      ["ice"],
		"slime":      ["slime"],
		"water":      ["water"],
	}

	# extension for (per-shader) option files
	slothFileExt     = ".sloth"

	# basename of the per-set option file
	defaultSlothFile = "options"+slothFileExt


	def __init__(self):
		self.sets             = dict() # set name -> shader name -> key -> value
		self.header           = ""     # header to be prepended to output
		self.suffixes         = dict() # map type -> suffix
		self.setSuffixes()

		# default options that can be overwritten on a per-folder/shader basis
		self["options"]                     = dict()
		self["options"]["lightColors"]      = dict() # color name -> RGB color triple
		self["options"]["customLights"]     = dict() # intensity name -> intensity; for grayscale addition maps
		self["options"]["predefLights"]     = dict() # intensity name -> intensity; for non-grayscale addition maps
		self["options"]["guessKeywords"]    = False  # whether to try to guess additional keywords based on shader (meta)data
		self["options"]["radToAddExp"]      = 1.0    # exponent used to convert radiosity RGB values into addition map color modifiers
		self["options"]["heightNormalsMod"] = 1.0    # modifier used when generating normals from height maps
		self["options"]["alphaTest"]        = None   # whether to use an alphaFunc/alphaTest keyword or smooth blending (default)
		self["options"]["alphaShadows"]     = True   # whether to add the alphashadows surfaceparm keyword to relevant shaders


	##################
	# GLOBAL OPTIONS #
	##################


	def setHeader(self, text):
		"Sets a header text to be put at the top of the shader file."
		self.header = text


	def setSuffixes(self, diffuse = "_d", normal = "_n", height = "_h", specular = "_s", addition = "_a", preview = "_p"):
		"Sets the filename suffixes for the different texture map types."
		self.suffixes["diffuse"]  = diffuse
		self.suffixes["normal"]   = normal
		self.suffixes["height"]   = height
		self.suffixes["specular"] = specular
		self.suffixes["addition"] = addition
		self.suffixes["preview"]  = preview


	######################
	# PER-SHADER OPTIONS #
	######################


	def __setKeywordGuessing(self, value, shader = None):
		if not shader:
			shader = self

		shader["options"]["guessKeywords"] = value

	def setKeywordGuessing(self, value = True):
		"Whether to try to guess additional keywords based on shader (meta)data"
		self.__setKeywordGuessing(value)


	def __setRadToAddExponent(self, value, shader = None):
		if not shader:
			shader = self

		shader["options"]["radToAddExp"] = value

	def setRadToAddExponent(self, value):
		"Set the exponent used to convert radiosity RGB values into addition map color modifiers"
		self.__setRadToAddExponent(value)


	def __setHeightNormalsMod(self, value, shader = None):
		if not shader:
			shader = self

		shader["options"]["heightNormalsMod"] = value

	def setHeightNormalsMod(self, value):
		"Set the modifier used when generating normals from height maps"
		self.__setHeightNormalsMod(value)


	def __setAlphaTest(self, test, shader = None):
		if not shader:
			shader = self

		if type(test) == float and 0 <= test <= 1:
			shader["options"]["alphaTest"] = test
		elif type(test) == str and test in ("GT0", "GE128", "LT128"):
			shader["options"]["alphaTest"] = test
		elif test == None:
			shader["options"]["alphaTest"] = None
		else:
			print("Alpha test must be either None, a valid string or a float between 0 and 1.", file = sys.stderr)

	def setAlphaTest(self, test):
		"Set the alpha test method used, blend smoothly if None."
		self.__setAlphaTest(test)


	def __setAlphaShadows(self, value, shader = None):
		if not shader:
			shader = self

		shader["options"]["alphaShadows"] = value

	def setAlphaShadows(self, value = True):
		"Whether to add the alphashadows surfaceparm keyword to relevant shaders"
		self.__setAlphaShadows(value)


	def __addLightColor(self, name, color, shader = None):
		if not shader:
			shader = self

		if not self.colorRE.match(color):
			print("Not a valid color: "+color+". Format is [0-9][a-f]{6}.", file = sys.stderr)
			return

		r = int(color[0:2], 16)
		g = int(color[2:4], 16)
		b = int(color[4:6], 16)

		if name in shader["options"]["lightColors"] and (r, g, b) != shader["options"]["lightColors"][name]:
			print("Overwriting light color "+name+": "+"%02x%02x%02x" % shader["options"]["lightColors"][name]+\
			      " -> "+color, file = sys.stderr)

		shader["options"]["lightColors"][name] = (r, g, b)

	def addLightColor(self, name, color):
		"Adds a light color with a given name to be used for light emitting shaders."
		self.__addLightColor(name, color)


	def __addLightIntensity(self, intensity, custom, shader = None):
		if not shader:
			shader = self

		intensity = int(intensity)

		if intensity < 0:
			print("Ignoring negative light intensity.", file = sys.stderr)["meta"]
			return

		if intensity >= 10000:
			name = str(int(intensity / 1000)) + "k"
		elif intensity == 0:
			name = "norad"
		else:
			name = str(intensity)

		if custom:
			shader["options"]["customLights"][name] = intensity
		else:
			shader["options"]["predefLights"][name] = intensity

	def addCustomLightIntensity(self, intensity):
		"Adds a light intensity to be used for light emitting shaders with grayscale addition maps."
		self.__addLightIntensity(intensity, True)

	def addPredefLightIntensity(self, intensity):
		"Adds a light intensity to be used for light emitting shaders with non-grayscale addition maps."
		self.__addLightIntensity(intensity, False)


	#################
	# FUNCTIONALITY #
	#################


	def __copyOptions(self, source, target):
		"Copies initial shader options."
		target["options"] = copy.deepcopy(source["options"])


	def __parseSlothFile(self, shader, path):
		"Parses a per-shader option file."
		config = configparser.ConfigParser()

		# parse file
		try:
			with open(path, "r") as fp:
				config.readfp(fp)
		except IOError:
			print("Couldn't read "+path+".", file = sys.stderr)
			return
		except configparser.ParsingError as error:
			print("Sloth file "+path+" contains an error:\n"+str(error), file = sys.stderr)
			return

		print("Parsing per-folder options file: "+path, file = sys.stderr)

		# parse options
		if "light" in config:
			options = config["light"]

			if "colors" in options:
				shader["options"]["lightColors"].clear()

				for nameAndColor in options["colors"].split():
					try:
						name, color = nameAndColor.split(":")
					except ValueError:
						continue
					self.__addLightColor(name, color, shader)

			if "add_colors" in options:
				for nameAndColor in options["add_colors"].split():
					try:
						name, color = nameAndColor.split(":")
					except ValueError:
						continue
					self.__addLightColor(name, color, shader)

			if "predef_lights" in options:
				shader["options"]["predefLights"].clear()

				for intensity in options["predef_lights"].split():
					self.__addLightIntensity(int(intensity), False, shader)

			if "add_predef_lights" in options:
				for intensity in options["add_predef_lights"].split():
					self.__addLightIntensity(int(intensity), False, shader)

			if "custom_lights" in options:
				shader["options"]["customLights"].clear()

				for intensity in options["custom_lights"].split():
					self.__addLightIntensity(int(intensity), True, shader)

			if "add_custom_lights" in options:
				for intensity in options["add_custom_lights"].split():
					self.__addLightIntensity(int(intensity), True, shader)

			if "color_blend_exp" in options:
				self.__setRadToAddExponent(options["color_blend_exp"], shader)


	def __analyzeMaps(self, shader):
		"Retrieves metadata from a shader's maps, such as whether there's an alpha channel on the diffuse map."
		# diffuse map
		img = Image.open(shader["abspath"]+os.path.sep+shader["diffuse"]+shader["ext"]["diffuse"], "r")
		shader["meta"]["diffuseAlpha"] = ( img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info) )

		# addition map
		if shader["addition"]:
			img = Image.open(shader["abspath"]+os.path.sep+shader["addition"]+shader["ext"]["addition"], "r")
			shader["meta"]["additionGrayscale"] = ( img.mode in ("L", "LA") )
		else:
			shader["meta"]["additionGrayscale"] = False


	def __addKeywords(self, shader):
		"Adds keywords based on knowledge (and potentially assumptions) about the shader (meta)data."
		shader.setdefault("keywords", dict())

		# transparent diffuse map
		if shader["meta"]["diffuseAlpha"]:
			shader["keywords"]["cull"] = "none"

			if shader["options"]["alphaTest"]:
				if type(shader["options"]["alphaTest"]) == str:
					shader["keywords"]["alphaFunc"] = shader["options"]["alphaTest"]
				else:
					shader["keywords"]["alphaTest"] = "%.2f" % shader["options"]["alphaTest"]

			if shader["options"]["alphaShadows"]:
				shader["keywords"].setdefault("surfaceparm", set())
				shader["keywords"]["surfaceparm"].add("alphashadows")

		if shader["options"]["guessKeywords"]:
			# guess surfaceParms
			for surfaceParm, words in self.surfaceParms.items():
				for word in words:
					if word in shader["name"]:
						shader["keywords"].setdefault("surfaceparm", set())
						shader["keywords"]["surfaceparm"].add(surfaceParm)


	def __expandLightShaders(self, setname):
		"Replaces every shader with an addition map with a set of shaders for each light color/intensity combination "
		"(only intensity for non-grayscale addition maps) as well as a not glowing version."
		newShaders = dict()
		delNames   = set()

		for shadername in self.sets[setname]:
			shader = self.sets[setname][shadername]

			if shader["addition"]:
				# mark original shader for deletion
				delNames.add(shadername)

				if shader["meta"]["additionGrayscale"]:
					# the addition map is grayscale, so
					for colorName, (r, g, b) in shader["options"]["lightColors"].items():
						for intensityName, intensity in shader["options"]["customLights"].items():
							newShader = copy.deepcopy(shader)

							newShader["meta"]["lightIntensity"]  = intensity
							newShader["meta"]["lightColor"]      = {"r": r, "g": g, "b": b}

							newShaders[shadername+"_"+colorName+"_"+intensityName] = newShader
				else:
					for intensityName, intensity in shader["options"]["predefLights"].items():
						newShader = copy.deepcopy(shader)

						newShader["meta"]["lightIntensity"]  = intensity

						newShaders[shadername+"_"+intensityName] = newShader

				# remove addition map from original shader and append "_off" to its name
				shader["addition"] = None
				newShaders[shadername+"_off"] = shader

		# delete old reference to the original
		for shadername in delNames:
			self.sets[setname].pop(shadername)

		# add new shaders (adds back original shader under new name, without addition map)
		self.sets[setname].update(newShaders)


	def generateSet(self, path, setname = None, cutextension = None):
		"Generates shader data for a given texture source folder."
		abspath    = os.path.abspath(path)
		root       = os.path.basename(os.path.abspath(path+os.path.sep+os.path.pardir))
		relpath    = root+"/"+os.path.basename(abspath)
		filelist   = os.listdir(abspath)
		mapsbytype = dict() # map type -> set of filenames without extentions
		mapext     = dict() # map name (no extension) -> map filename (with extension)
		slothfiles = set()  # sloth per-shader config file names (no extension)

		# retrieve all maps by type
		for filename in filelist:
			mapname, ext = os.path.splitext(filename)

			if ext == self.slothFileExt:
				slothfiles.add(mapname)
			else:
				for (maptype, suffix) in self.suffixes.items():
					mapsbytype.setdefault(maptype, set())

					if mapname.endswith(suffix):
						mapext[mapname] = ext
						mapsbytype[maptype].add(mapname)

		# add a new set or extend the current one
		if not setname:
			if cutextension and len(cutextension) > 0:
				setname = relpath.rsplit(cutextension)[0]
			else:
				setname = relpath

		self.sets.setdefault(setname, dict())

		# parse per-folder options
		options = dict()

		self.__copyOptions(self, options)

		if self.defaultSlothFile in filelist:
			self.__parseSlothFile(options, abspath+os.path.sep+self.defaultSlothFile)

		# add a shader for each diffuse map
		for diffusename in mapsbytype["diffuse"]:
			shadername = diffusename.rsplit(self.suffixes["diffuse"])[0]

			# add a new shader
			shader = self.sets[setname][shadername] = dict()

			# copy default options
			self.__copyOptions(options, shader)

			# init shader data
			shader["name"]            = shadername
			shader["relpath"]         = relpath
			shader["abspath"]         = abspath
			shader["diffuse"]         = diffusename
			shader["ext"]             = {"diffuse": mapext[diffusename]}
			shader["meta"]            = dict()

			# attempt to find a map of every known non-diffuse type
			# assumes that non-diffuse map names form the start of diffuse map names
			for maptype, suffix in self.suffixes.items():
				basename = shadername

				while basename != "":
					mapname = basename+suffix

					if mapname in mapsbytype[maptype]:
						if mapname in slothfiles:
							# parse per-shader options
							self.__parseSlothFile(shader, abspath+os.path.sep+mapname+self.slothFileExt)
						else:
							shader[maptype]        = mapname
							shader["ext"][maptype] = mapext[mapname]
						break

					basename = basename[:-1]

				if basename == "": # no map of this type found
					shader[maptype]        = None
					shader["ext"][maptype] = None

			# retrieve more metadata from the maps
			self.__analyzeMaps(shader)

			# now that we have enough knowledge about the shader, add keywords
			self.__addKeywords(shader)

		numVariants = str(len(self.sets[setname]))

		# expand relevant shaders into multiple light emitting ones
		self.__expandLightShaders(setname)

		numShaders = str(len(self.sets[setname]))

		print(setname+": Added "+numShaders+" shaders for "+numVariants+" texture variants.", file = sys.stderr)


	def clearSets(self):
		"Forgets about all shader data that has been generated."
		self.sets.clear()


	def __radToAdd(self, shader, r, g = None, b = None):
		"Given light colors, return modified colors to be used in the blend phase of the addition map."
		exp = shader["options"]["radToAddExp"]

		if g and b:
			return (r**exp, g**exp, b**exp)
		else:
			return r**exp


	def getShader(self, setname = None, shadername = None):
		"Assembles and returns the shader file content."
		content = ""

		for line in self.header.splitlines():
			if line.startswith("//"):
				content += line+"\n"
			else:
				content += "// "+line+"\n"

		if setname:
			if setname in self.sets:
				setnames = (setname, )
			else:
				print("Unknown set "+str(setname)+".", file = sys.stderr)
				return
		else:
			setnames = self.sets.keys()

		for setname in setnames:
			if shadername:
				if shadername in self.sets[setname]:
					names = (shadername, )
				else:
					continue
			else:
				content += "\n"+\
				           "// "+"-"*len(setname)+"\n"+\
				           "// "+setname+"\n"+\
				           "// "+"-"*len(setname)+"\n"

				names = sorted(self.sets[setname].keys())

			for shadername in names:
				# prepare content
				shader = self.sets[setname][shadername]
				path   = shader["relpath"]+"/"

				# decide on a preview image
				if shader["preview"]:
					preview = shader["preview"]
				elif shader["diffuse"]:
					preview = shader["diffuse"]
				else:
					preview = None

				# extract light color if available
				if "lightColor" in shader["meta"]:
					r = shader["meta"]["lightColor"]["r"] / 0xff
					g = shader["meta"]["lightColor"]["g"] / 0xff
					b = shader["meta"]["lightColor"]["b"] / 0xff

				content += "\n"+setname+"/"+shadername+"\n{\n"

				# preview image
				if preview:
					content += "\tqer_editorImage     "+path+preview+"\n\n"

				# keywords
				if "keywords" in shader and len(shader["keywords"]) > 0:
					for key, value in sorted(shader["keywords"].items()):
						if type(value) != str and hasattr(value, "__iter__"):
							for value in sorted(value):
								content += "\t"+key+" "*max(1, 20-len(key))+str(value)+"\n"
						else:
							content += "\t"+key+" "*max(1, 20-len(key))+str(value)+"\n"
					content += "\n"

				# surface light
				if "lightIntensity" in shader["meta"] and shader["meta"]["lightIntensity"] > 0:
					# intensity
					content += "\tq3map_surfacelight  "+"%d" % shader["meta"]["lightIntensity"]+"\n"

					# color
					if "lightColor" in shader["meta"]:
						content += "\tq3map_lightRGB      "+"%.2f %.2f %.2f" % (r, g, b)+"\n\n"
					elif shader["addition"]:
						content += "\tq3map_lightImage    "+shader["addition"]+"\n\n"
					elif shader["diffuse"]:
						content += "\tq3map_lightImage    "+shader["diffuse"]+"\n\n"
					else:
						content += "\tq3map_lightRGB      1.00 1.00 1.00\n\n"

				# diffuse map
				if shader["diffuse"]:
					if shader["meta"]["diffuseAlpha"] and not shader["options"]["alphaTest"]:
						content += "\t{\n"+\
						           "\t\tmap   "+path+shader["diffuse"]+"\n"+\
						           "\t\tblend blend\n"+\
						           "\t}\n"
					else:
						content += "\tdiffuseMap          "+path+shader["diffuse"]+"\n"

				# normal & height map
				if shader["normal"]:
					if shader["height"] and shader["options"]["heightNormalsMod"] > 0:
						content += "\tnormalMap           addnormals ( "+path+shader["normal"]+\
						           ", heightmap ( "+path+shader["height"]+", "+\
						           "%.2f" % shader["options"]["heightNormalsMod"]+" ) )\n"
					else:
						content += "\tnormalMap           "+path+shader["normal"]+"\n"
				elif shader["height"] and shader["options"]["heightNormalsMod"] > 0:
					content += "\tnormalMap           heightmap ( "+path+shader["height"]+", "+\
						       "%.2f" % shader["options"]["heightNormalsMod"]+" )\n"

				# specular map
				if shader["specular"]:
					content += "\tspecularMap         "+path+shader["specular"]+"\n"

				# addition map
				if shader["addition"]:
					content += "\t{\n"+\
							   "\t\tmap   "+path+shader["addition"]+"\n"+\
							   "\t\tblend add\n"
					if "lightColor" in shader["meta"]:
						content += \
							   "\t\tred   "+"%.2f" % self.__radToAdd(shader, r)+"\n"+\
							   "\t\tgreen "+"%.2f" % self.__radToAdd(shader, g)+"\n"+\
							   "\t\tblue  "+"%.2f" % self.__radToAdd(shader, b)+"\n"
					content += \
							   "\t}\n"

				content += "}\n"

		return content


if __name__ == "__main__":
	# parse command line options
	p = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
	                            description="Generates XreaL/Daemon shader files from directories of texture maps.")

	# Misc arguments
	p.add_argument("pathes", metavar="PATH", nargs="+",
	               help="Path to a source directory that should be added to the set")

	p.add_argument("-g", "--guess", action="store_true",
	               help="Guess additional keywords based on shader (meta)data")

	p.add_argument("--height-normals", metavar="VALUE", type=float, default=1.0,
	               help="Modifier used for generating normals from a heightmap")

	# Texture map suffixes
	g = p.add_argument_group("Texture map suffixes")

	g.add_argument("-d", "--diff",   metavar="SUF", default="_d", help="Suffix used by diffuse maps")
	g.add_argument("-n", "--normal", metavar="SUF", default="_n", help="Suffix used by normal maps")
	g.add_argument("-z", "--height", metavar="SUF", default="_h", help="Suffix used by height maps")
	g.add_argument("-s", "--spec",   metavar="SUF", default="_s", help="Suffix used by specular maps")
	g.add_argument("-a", "--add",    metavar="SUF", default="_a", help="Suffix used by addition/glow maps")
	g.add_argument("-p", "--prev",   metavar="SUF", default="_p", help="Suffix used by preview images")

	# Light emitting shaders
	g = p.add_argument_group("Light emitting shaders")

	g.add_argument("-c", "--colors", metavar="NAME:COLOR", nargs="+", default=["white:ffffff"],
	               help="Add light colors with the given name, using a RGB hex triplet. "
	                    "They will only be used in combination with grayscale addition maps.")

	g.add_argument("-l", "--custom-lights", metavar="VALUE", type=int, nargs="+", default=[1000,2000,4000],
	               help="Add light intensities for light emitting shaders with custom colors (grayscale addition map)")

	g.add_argument("-i", "--predef-lights", metavar="VALUE", type=int, nargs="+", default=[0,200],
	               help="Add light intensities for light emitting shaders with predefined colors (non-grayscale addition map)")

	g.add_argument("--color-blend-exp", metavar="VALUE", type=float, default=1.0,
	               help="Exponent applied to custom light color channels for use in the addition map blend phase")

	# Alpha blending
	g = p.add_argument_group("Alpha blending")
	gm = g.add_mutually_exclusive_group()

	gm.add_argument("--gt0", action="store_true",
	               help="Use alphaFunc GT0 instead of smooth alpha blending.")

	gm.add_argument("--ge128", action="store_true",
	               help="Use alphaFunc GE128 instead of smooth alpha blending.")

	gm.add_argument("--lt128", action="store_true",
	               help="Use alphaFunc LT128 instead of smooth alpha blending.")

	gm.add_argument("--alpha-test", metavar="VALUE", type=float,
	               help="Use alphaTest instead of smooth alpha blending.")

	g.add_argument("--no-alpha-shadows", action="store_true",
	               help="Don't add the alphashadows surfaceparm.")

	# Input & Output
	g = p.add_argument_group("Input & Output")
	gm = g.add_mutually_exclusive_group()

	gm.add_argument("-r", "--root",
	               help="Sets the namespace for the set (e.g. textures/setname). "
	                    "Can be used to merge source folders into a single set.")

	gm.add_argument("-x", "--strip", metavar="SUF", default="_src",
	               help="Strip suffix from source folder names when generating the set name")

	g.add_argument("-t", "--header", metavar="FILE", type=argparse.FileType("r"),
	               help="Use file content as a header, \"// \" will be prepended to each line")

	g.add_argument("-o", "--out", metavar="DEST", type=argparse.FileType("w"),
	               help="Write shader to this file")

	a = p.parse_args()

	# init generator
	sg = ShaderGenerator()

	sg.setSuffixes(diffuse = a.diff, normal = a.normal, height = a.height,
	               specular = a.spec, addition = a.add, preview = a.prev)

	sg.setKeywordGuessing(a.guess)
	sg.setRadToAddExponent(a.color_blend_exp)
	sg.setHeightNormalsMod(a.height_normals)
	sg.setAlphaShadows(not a.no_alpha_shadows)

	if a.header:
		sg.setHeader(a.header.read())
		a.header.close()

	for (name, color) in [item.split(":") for item in a.colors]:
		sg.addLightColor(name, color)

	for intensity in a.custom_lights:
		sg.addCustomLightIntensity(intensity)

	for intensity in a.predef_lights:
		sg.addPredefLightIntensity(intensity)

	if a.alpha_test:
		sg.setAlphaTest(a.alpha_test)
	elif a.gt0:
		sg.setAlphaTest("GT0")
	elif a.ge128:
		sg.setAlphaTest("GE128")
	elif a.lt128:
		sg.setAlphaTest("LT128")

	# generate
	for path in a.pathes:
		sg.generateSet(path, setname = a.root, cutextension = a.strip)

	# output
	shader = sg.getShader()

	if a.out:
		a.out.write(shader)
		a.out.close()
	else:
		print(shader)
