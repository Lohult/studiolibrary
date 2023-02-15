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
"""
NOTE: Make sure you register this item in the config.
"""

import os
import logging

from studiolibrarymaya import baseitem

try:
    import mutils
    import mutils.gui
    import maya.cmds
except ImportError as error:
    print(error)


logger = logging.getLogger(__name__)

def save(path, *args, **kwargs):
    """Convenience function for saving an AnimItem."""
    CacheItem(path).safeSave(*args, **kwargs)


def load(path, *args, **kwargs):
    """Convenience function for loading an AnimItem."""
    CacheItem(path).load(*args, **kwargs)


class CacheItem(baseitem.BaseItem):

    NAME = "Cache"
    EXTENSION = ".abc"
    ICON_PATH = os.path.join(os.path.dirname(__file__), "icons", "cache.png")
    TRANSFER_CLASS = mutils.Cache

    def imageSequencePath(self):
        """
        Return the image sequence location for playing the animation preview.

        :rtype: str
        """
        return self.path() + "/sequence"

    def loadSchema(self):
        """
        Get schema used to load the animation item.

        :rtype: list[dict]
        """
        schema = super(CacheItem, self).loadSchema()

        cache = mutils.Cache.fromPath(self.path())

        startFrame = cache.startFrame() or 0
        endFrame = cache.endFrame() or 0

        value = "{0} - {1}".format(startFrame, endFrame)
        schema.insert(3, {"name": "Range", "value": value})

        # schema.extend([
        #     {
        #         "name": "optionsGroup",
        #         "title": "Options",
        #         "type": "group",
        #         "order": 2,
        #     }
        # ])

        return schema

    def load(self, **kwargs):
        """
        Load the cache for the given objects and options.

        :type kwargs: dict
        """
        cache = mutils.Cache.fromPath(self.path())
        cache.load(
            objects=kwargs.get("objects"),
            namespaces=kwargs.get("namespaces"),
        )

    def saveSchema(self):
        """
        Get the schema for saving an animation item.

        :rtype: list[dict]
        """
        start, end = (1, 100)

        try:
            start, end = mutils.currentFrameRange()
        except NameError as error:
            logger.exception(error)

        return [
            {
                "name": "folder",
                "type": "path",
                "layout": "vertical",
                "visible": False,
            },
            {
                "name": "name",
                "type": "string",
                "layout": "vertical"
            },
            {
                "name": "fileType",
                "type": "enum",
                "layout": "vertical",
                "default": "Alembic",
                "items": ["Alembic"],
                "persistent": True
            },
            {
                "name": "exportUSD",
                "type": "bool",
                "default": False,
                "persistent": True,
                "inline": True,
                "label": {"visible": False}
            },
            {
                "name": "frameRange",
                "type": "range",
                "layout": "vertical",
                "default": [start, end],
                "actions": [
                    {
                        "name": "From Timeline",
                        "callback": mutils.playbackFrameRange
                    },
                    {
                        "name": "From Selected Timeline",
                        "callback": mutils.selectedFrameRange
                    }
                ]
            },
            {
                "name": "byFrame",
                "type": "int",
                "default": 1,
                "layout": "vertical",
                "persistent": True
            },
            {
                "name": "comment",
                "type": "text",
                "layout": "vertical"
            },
            {
                "name": "objects",
                "type": "objects",
                "label": {
                    "visible": False
                }
            },
        ]

    def saveValidator(self, **kwargs):
        """
        The save validator is called when an input field has changed.

        :type kwargs: dict
        :rtype: list[dict]
        """
        fields = super(CacheItem, self).saveValidator(**kwargs)

        # Validate the by frame field
        if kwargs.get("byFrame") == '' or kwargs.get("byFrame", 1) < 1:
            fields.extend([
                {
                    "name": "byFrame",
                    "error": "The by frame value cannot be less than 1!"
                }
            ])

        # Validate the frame range field
        start, end = kwargs.get("frameRange", (0, 1))
        if start >= end:
            fields.extend([
                {
                    "name": "frameRange",
                    "error":  "The start frame cannot be greater "
                              "than or equal to the end frame!"
                }
            ])

        return fields

    def save(self, objects, sequencePath="", **kwargs):
        """
        Cache the geometry from the given objects to the item path.
        
        :type objects: list[str]
        :type sequencePath: str
        :type kwargs: dict
        """
        super(CacheItem, self).save(**kwargs)

        # Save the animation to the given path location on disc
        mutils.exportAbc(
            objects,
            self.path(),
            time=kwargs.get("frameRange"),
            fileType=kwargs.get("fileType"),
            iconPath=kwargs.get("thumbnail"),
            metadata={"description": kwargs.get("comment", "")},
            sequencePath=sequencePath,
            exportUSD=kwargs.get("exportUSD")
        )
