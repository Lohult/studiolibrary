# Copyright 2020 by Kurt Rathjen. All Rights Reserved.
#
# This library is free software: you can redistribute it and/or modify it 
# under the terms of the GNU Lesser General Public License as published by 
# the Free Software Foundation, either version 3 of the License, or 
# (at your option) any later version. This library is distributed in the 
# hope that it will be useful, but WITHOUT ANY WARRANTY; without even the 
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. 
# See the GNU Lesser General Public License for more details.
# You should have received a copy of the GNU Lesser General Public
# License along with this library. If not, see <http://www.gnu.org/licenses/>.

import os
import shutil
import logging

from studiovendor.Qt import QtWidgets

import mutils
import mutils.gui

try:
    import maya.cmds
except ImportError:
    import traceback
    traceback.print_exc()

logger = logging.getLogger(__name__)


MIN_TIME_LIMIT = -10000
MAX_TIME_LIMIT = 100000
DEFAULT_FILE_TYPE = "Alembic"

# A feature flag that will be removed in the future.
FIX_SAVE_ANIM_REFERENCE_LOCKED_ERROR = True


class PasteOption:

    Replace = "replace"
    Import = "import"
    # Replace = "replace"
    # ReplaceAll = "replace all"
    # ReplaceCompletely = "replaceCompletely"


class AnimationTransferError(Exception):
    """Base class for exceptions in this module."""
    pass


class OutOfBoundsError(AnimationTransferError):
    """Exceptions for clips or ranges that are outside the expected range"""
    pass

def exportAbc(
        objects,
        path,
        time=None,
        sampleBy=1,
        fileType="Alembic",
        exportUSD=False,
        metadata=None,
        iconPath="",
        sequencePath=""
):
    """
    Save the cache data for the given objects.

    Example:
        import mutils
        mutils.saveAnim(
            path="c:/example.abc", 
            objects=["control1", "control2"]
            time=(1, 20),
            metadata={'description': 'Example cache'}
            )
            
    :type path: str
    :type objects: None or list[str]
    :type time: (int, int) or None
    :type fileType: str or None
    :type sampleBy: int
    :type iconPath: str
    :type sequencePath: str
    :type metadata: dict or None
    :type bakeConnected: bool
    
    :rtype: mutils.Animation
    """
    # Copy the icon path to the temp location
    if iconPath:
        shutil.copyfile(iconPath, path + "/thumbnail.jpg")

    # Copy the sequence path to the temp location
    if sequencePath:
        shutil.move(sequencePath, path + "/sequence")

    # Save the animation to the temp location
    cache = mutils.Cache.fromObjects(objects)
    cache.updateMetadata(metadata)
    cache.save(
        path,
        time=time,
        sampleBy=sampleBy,
        fileType=fileType,
        exportUSD=exportUSD
    )
    return cache


def clampRange(srcTime, dstTime):
    """
    Clips the given source time to within the given destination time.

    Example:
        print clampRange((15, 35), (20, 30))
        # 20, 30

        print clampRange((25, 45), (20, 30))
        # 25, 30

    :type srcTime: (int, int)
    :type dstTime: (int, int)
    :rtype: (int, int)
    """
    srcStart, srcEnd = srcTime
    dstStart, dstEnd = dstTime

    if srcStart > dstEnd or srcEnd < dstStart:
        msg = "The src and dst time do not overlap. " \
              "Unable to clamp (src=%s, dest=%s)"
        raise OutOfBoundsError(msg, srcTime, dstTime)

    if srcStart < dstStart:
        srcStart = dstStart

    if srcEnd > dstEnd:
        srcEnd = dstEnd

    return srcStart, srcEnd


def moveTime(time, start):
    """
    Move the given time to the given start time.

    Example:
        print moveTime((15, 35), 5)
        # 5, 20

    :type time: (int, int)
    :type start: int
    :rtype: (int, int)
    """
    srcStartTime, srcEndTime = time
    duration = srcEndTime - srcStartTime

    if start is None:
        startTime = srcStartTime
    else:
        startTime = start

    endTime = startTime + duration

    if startTime == endTime:
        endTime = startTime + 1

    return startTime, endTime


def findFirstLastKeyframes(curves, time=None):
    """
    Return the first and last frame of the given animation curves

    :type curves: list[str]
    :type time: (int, int)
    :rtype: (int, int)
    """
    first = maya.cmds.findKeyframe(curves, which='first')
    last = maya.cmds.findKeyframe(curves, which='last')

    result = (first, last)

    if time:

        # It's possible (but unlikely) that the curves will not lie within the
        # first and last frame
        try:
            result = clampRange(time, result)
        except OutOfBoundsError as error:
            logger.warning(error)

    return result


def insertKeyframe(curves, time):
    """
    Insert a keyframe on the given curves at the given time.

    :type curves: list[str]
    :type time: (int, int)
    """
    startTime, endTime = time

    for curve in curves:
        insertStaticKeyframe(curve, time)

    firstFrame = maya.cmds.findKeyframe(curves, time=(startTime, startTime), which='first')
    lastFrame = maya.cmds.findKeyframe(curves, time=(endTime, endTime), which='last')

    if firstFrame < startTime < lastFrame:
        maya.cmds.setKeyframe(curves, insert=True, time=(startTime, startTime))

    if firstFrame < endTime < lastFrame:
        maya.cmds.setKeyframe(curves, insert=True, time=(endTime, endTime))


def insertStaticKeyframe(curve, time):
    """
    Insert a static keyframe on the given curve at the given time.

    :type curve: str
    :type time: (int, int)
    :rtype: None
    """
    startTime, endTime = time

    lastFrame = maya.cmds.findKeyframe(curve, which='last')
    firstFrame = maya.cmds.findKeyframe(curve, which='first')

    if firstFrame == lastFrame:
        maya.cmds.setKeyframe(curve, insert=True, time=(startTime, endTime))
        maya.cmds.keyTangent(curve, time=(startTime, startTime), ott="step")

    if startTime < firstFrame:
        nextFrame = maya.cmds.findKeyframe(curve, time=(startTime, startTime), which='next')
        if startTime < nextFrame < endTime:
            maya.cmds.setKeyframe(curve, insert=True, time=(startTime, nextFrame))
            maya.cmds.keyTangent(curve, time=(startTime, startTime), ott="step")

    if endTime > lastFrame:
        previousFrame = maya.cmds.findKeyframe(curve, time=(endTime, endTime), which='previous')
        if startTime < previousFrame < endTime:
            maya.cmds.setKeyframe(curve, insert=True, time=(previousFrame, endTime))
            maya.cmds.keyTangent(curve, time=(previousFrame, previousFrame), ott="step")


def importAbc(
    paths,
    spacing=1,
    objects=None,
    option=None,
    namespaces=None,
    showDialog=False,
):
    """
    Load the animations in the given order of paths with the spacing specified.

    :type paths: list[str]
    :type spacing: int
    :type objects: list[str]
    :type namespaces: list[str]
    :type startFrame: int
    :type option: PasteOption
    :type showDialog: bool
    """
    isFirstAnim = True

    if spacing < 1:
        spacing = 1

    if option is None or option == "replace all":
        option = PasteOption.ReplaceCompletely

    if showDialog:

        msg = "Load the following animation in sequence;\n"

        for i, path in enumerate(paths):
            msg += "\n {0}. {1}".format(i, os.path.basename(path))

        msg += "\n\nPlease choose the spacing between each animation."

        spacing, accepted = QtWidgets.QInputDialog.getInt(
            None,
            "Load animation sequence",
            msg,
            spacing,
            QtWidgets.QInputDialog.NoButtons,
        )

        if not accepted:
            raise Exception("Dialog canceled!")

    for path in paths:

        cache = mutils.Cache.fromPath(path)

        if startFrame is None and isFirstAnim:
            startFrame = cache.startFrame()

        if option == "replaceCompletely" and not isFirstAnim:
            option = "insert"

        cache.load(
            option=option,
            objects=objects,
            startFrame=startFrame,
            namespaces=namespaces,
        )

        duration = cache.endFrame() - cache.startFrame()
        startFrame += duration + spacing
        isFirstAnim = False


class Cache(mutils.Pose):

    IMPORT_NAMESPACE = "REMOVE_IMPORT"

    @classmethod
    def fromPath(cls, path):
        """
        Create and return an Anim object from the give path.

        Example:
            cache = Animation.fromPath("/temp/example.abc")
            print cache.endFrame()
            # 14

        :type path: str
        :rtype: Animation
        """
        cache = cls()
        cache.setPath(path)
        cache.read()
        return cache

    def __init__(self):
        mutils.Pose.__init__(self)

        try:
            timeUnit = maya.cmds.currentUnit(q=True, time=True)
            linearUnit = maya.cmds.currentUnit(q=True, linear=True)
            angularUnit = maya.cmds.currentUnit(q=True, angle=True)

            self.setMetadata("timeUnit", timeUnit)
            self.setMetadata("linearUnit", linearUnit)
            self.setMetadata("angularUnit", angularUnit)
        except NameError as msg:
            logger.exception(msg)

    def select(self, objects=None, namespaces=None, **kwargs):
        """
        Select the objects contained in the animation.
        
        :type objects: list[str] or None
        :type namespaces: list[str] or None
        :rtype: None
        """
        selectionSet = mutils.SelectionSet.fromPath(self.poseJsonPath())
        selectionSet.load(objects=objects, namespaces=namespaces, **kwargs)

    def startFrame(self):
        """
        Return the start frame for cache object.

        :rtype: int
        """
        return self.metadata().get("startFrame")

    def endFrame(self):
        """
        Return the end frame for cache object.

        :rtype: int
        """
        return self.metadata().get("endFrame")

    def mayaPath(self):
        """
        :rtype: str
        """
        mayaPath = os.path.join(self.path(), "animation.mb")
        if not os.path.exists(mayaPath):
            mayaPath = os.path.join(self.path(), "animation.ma")
        return mayaPath

    def poseJsonPath(self):
        """
        :rtype: str
        """
        return os.path.join(self.path(), "pose.json")

    def paths(self):
        """
        Return all the paths for Anim object.

        :rtype: list[str]
        """
        result = []
        if os.path.exists(self.mayaPath()):
            result.append(self.mayaPath())

        if os.path.exists(self.poseJsonPath()):
            result.append(self.poseJsonPath())

        return result

    def animCurve(self, name, attr, withNamespace=False):
        """
        Return the animCurve for the given object name and attribute.

        :type name: str
        :type attr: str
        :type withNamespace: bool

        :rtype: str
        """
        curve = self.attr(name, attr).get("curve", None)
        if curve and withNamespace:
            curve = Cache.IMPORT_NAMESPACE + ":" + curve
        return curve

    def setAnimCurve(self, name, attr, curve):
        """
        Set the animCurve for the given object name and attribute.

        :type name: str
        :type attr: str
        :type curve: str
        """
        self.objects()[name].setdefault("attrs", {})
        self.objects()[name]["attrs"].setdefault(attr, {})
        self.objects()[name]["attrs"][attr]["curve"] = curve

    def read(self, path=None):
        """
        Read all the data to be used by the Anim object.

        :rtype: None
        """
        path = self.poseJsonPath()

        logger.debug("Reading: " + path)
        mutils.Pose.read(self, path=path)
        logger.debug("Reading Done")

    def isAscii(self, s):
        """Check if the given string is a valid ascii string."""
        return all(ord(c) < 128 for c in s)

    @mutils.unifyUndo
    @mutils.restoreSelection
    def open(self):
        """
        The reason we use importing and not referencing is because we
        need to modify the imported animation curves and modifying
        referenced animation curves is only supported in Maya 2014+
        """
        self.close()  # Make sure everything is cleaned before importing

        if not self.isAscii(self.mayaPath()):
            msg = "Cannot load animation using non-ascii paths."
            raise IOError(msg)

        nodes = maya.cmds.file(
            self.mayaPath(),
            i=True,
            groupLocator=True,
            ignoreVersion=True,
            returnNewNodes=True,
            namespace=Cache.IMPORT_NAMESPACE,
        )

        return nodes

    def close(self):
        """
        Clean up all imported nodes, as well as the namespace.
        Should be called in a finally block.
        """
        nodes = maya.cmds.ls(Cache.IMPORT_NAMESPACE + ":*", r=True) or []
        if nodes:
            maya.cmds.delete(nodes)

        # It is important that we remove the imported namespace,
        # otherwise another namespace will be created on next
        # animation open.
        namespaces = maya.cmds.namespaceInfo(ls=True) or []

        if Cache.IMPORT_NAMESPACE in namespaces:
            maya.cmds.namespace(set=':')
            maya.cmds.namespace(rm=Cache.IMPORT_NAMESPACE)

    def cleanMayaFile(self, path):
        """
        Clean up all commands in the exported maya file that are
        not createNode.
        """
        results = []

        with open(path, "r") as f:
            for line in f.readlines():
                if not line.startswith("select -ne"):
                    results.append(line)
                else:
                    results.append("// End")
                    break

        with open(path, "w") as f:
            f.writelines(results)

    def _duplicate_node(self, node_path, duplicate_name):
        """Duplicate given node.

        :param node_path: Maya path.
        :type node_path: str
        :param duplicate_name: Name for the duplicated node.
        :type duplicate_name: str
        :returns: Duplicated node.
        :rtype: str
        """
        if maya.cmds.nodeType(node_path) == "transform":
            duplicated_node = maya.cmds.duplicate(node_path,
                                                  name=duplicate_name,
                                                  parentOnly=True)[0]
        else:
            duplicated_node = maya.cmds.duplicate(node_path,
                                                  name=duplicate_name)[0]
            duplicated_node = maya.cmds.listRelatives(duplicated_node,
                                                      shapes=True)[0] or []

        return duplicated_node

    @mutils.timing
    @mutils.unifyUndo
    @mutils.showWaitCursor
    @mutils.restoreSelection
    def save(
        self,
        path,
        time=None,
        sampleBy=1,
        fileType="Alembic",
        exportUSD=False
    ):
        """
        Save all animation data from the objects set on the Anim object.

        :type path: str
        :type time: (int, int) or None
        :type sampleBy: int
        :type fileType: str
        
        :rtype: None
        """
        objects = list(self.objects().keys())

        fileType = fileType or DEFAULT_FILE_TYPE

        if not time:
            time = mutils.selectedObjectsFrameRange(objects)
        start, end = time

        # Check frame range
        if start is None or end is None:
            msg = "Please specify a start and end frame!"
            raise AnimationTransferError(msg)

        if start >= end:
            msg = "The start frame cannot be greater than or equal to the end frame!"
            raise AnimationTransferError(msg)

        self.setMetadata("endFrame", end)
        self.setMetadata("startFrame", start)

        end += 1

        msg = u"Cache.save(path={0}, time={1}, sampleBy={2}), exportUSD={3}"
        msg = msg.format(path, str(time), str(sampleBy), str(exportUSD))
        logger.debug(msg)

        fileName = "cache.abc"
        if fileType == "Alembic":
            fileName = "cache.abc"

        mayaPath = os.path.join(path, fileName)
        posePath = os.path.join(path, "pose.json")
        mutils.Pose.save(self, posePath)

        root_to_objects = []
        root_to_objects = []
        for object in objects:
            maya.cmds.ls(object, long=True)
            root_to_objects.append("-root " + object)
        root_to_objects = " ".join(root_to_objects)
        command = u"-frameRange {0} {1} -uvWrite -stripNamespaces -dataFormat ogawa {2} -file {3}"
        command = command.format(start, end, root_to_objects, mayaPath)
        maya.cmds.AbcExport ( j = command )

        try:
            if exportUSD:
                try:
                    import pymel.core as pmc
                    from mgear.core import dag
                except:
                    raise
                exportList = []
                for selection in pmc.selected():
                    topnode = dag.getTopParent(selection)
                    if topnode.hasAttr("is_crowd"):
                        exportList.append(topnode)
                if exportList:
                    maya.cmds.mayaUSDExport(
                        file=mayaPath.replace(".abc", ".usdc"),
                        frameRange=[start, end],
                        frameStride=1.0,
                        convertMaterialsTo="None",
                        exportColorSets=False,
                        exportInstances=False,
                        exportUVs=False,
                        kind='component',
                        exportDisplayColor=False,
                        shadingMode=None,
                        selection=True,
                        stripNamespaces=True,
                        verbose=True,
                        exportSkels="auto",
                        exportSkin=None,
                        exportBlendShapes=0,
                        eulerFilter=1,
                        staticSingleSample=1
                    )
                else:
                    logger.warning("USD not exported.")
        except:
            raise

        self.setPath(path)

    @mutils.timing
    @mutils.showWaitCursor
    def load(
            self,
            objects=None,
            namespaces=None,
            option=None,
    ):
        """
        Load the animation data to the given objects or namespaces.

        :type objects: list[str]
        :type namespaces: list[str]
        :type option: PasteOption or None
        """
        logger.info(u'Loading: {0}'.format(self.path()))

        sourceTime = (self.startFrame(), self.endFrame())

        # if option and option.lower() == "replace":
        #     option = "replaceCompletely"

        # if option is None or option == PasteOption.ReplaceAll:
        #     option = PasteOption.ReplaceCompletely

        self.validate(namespaces=namespaces)

        objects = objects or []

        logger.debug("Cache.load(objects=%s, option=%s, namespaces=%s, srcTime=%s)" %
                    (len(objects), str(option), str(namespaces), str(sourceTime)))


        logger.info(u'Loaded: {0}'.format(self.path()))
