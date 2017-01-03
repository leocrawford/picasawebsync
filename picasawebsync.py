#!/usr/bin/python

import os
import re
import argparse
import mimetypes
import hashlib
import time
import urllib
import fnmatch
import tempfile
import calendar
import httplib2
import threading

# from apiclient import discovery
from oauth2client import client
from subprocess import call
from datetime import timedelta, datetime

from gdata.photos.service import *
import gdata.media
import gdata.geo
from PIL import Image


PICASA_MAX_FREE_IMAGE_DIMENSION = 2048


def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


jHead = which('jhead')

# used https://github.com/jackpal/picasawebuploader/blob/master/main.py and 
# http://stackoverflow.com/questions/273946/how-do-i-resize-an-image-using-pil-and-maintain-its-aspect-ratio
def shrinkIfNeeded(path):
    if args.shrink:
        imagePath = tempfile.NamedTemporaryFile(delete=False)
        try:
            im = Image.open(path)
            if (im.size[0] > PICASA_MAX_FREE_IMAGE_DIMENSION or im.size[1] > PICASA_MAX_FREE_IMAGE_DIMENSION):
                print "Shrinking " + path
                im.thumbnail((PICASA_MAX_FREE_IMAGE_DIMENSION, PICASA_MAX_FREE_IMAGE_DIMENSION), Image.ANTIALIAS)
                im.save(imagePath, "JPEG")
                if (jHead is not None):
                    call(["jhead", "-q", "-te", path, imagePath.name])
                return imagePath.name
        except IOError:
            print "cannot create thumbnail for '%s' - using full size image" % path
    return None


# Borrowed from http://www.daniweb.com/software-development/python/code/216610/timing-a-function-python
def print_timing(func):
    def wrapper(*arg):
        t1 = time.time()
        res = func(*arg)
        t2 = time.time()
        print '%s took %0.3f ms' % (func.func_name, (t2 - t1) * 1000.0)
        return res

    return wrapper


# Upload video code came form http://nathanvangheem.com/news/moving-to-picasa-update
class VideoEntry(gdata.photos.PhotoEntry):
    pass


gdata.photos.VideoEntry = VideoEntry


def InsertVideo(self, album_or_uri, video, filename_or_handle, content_type='image/jpeg'):
    """Copy of InsertPhoto which removes protections since it *should* work"""
    try:
        assert (isinstance(video, VideoEntry))
    except AssertionError:
        raise GooglePhotosException({'status': GPHOTOS_INVALID_ARGUMENT,
                                     'body': '`video` must be a gdata.photos.VideoEntry instance',
                                     'reason': 'Found %s, not PhotoEntry' % type(video)
                                     })
    try:
        majtype, mintype = content_type.split('/')
    # assert(mintype in SUPPORTED_UPLOAD_TYPES)
    except (ValueError, AssertionError):
        raise GooglePhotosException({'status': GPHOTOS_INVALID_CONTENT_TYPE,
                                     'body': 'This is not a valid content type: %s' % content_type,
                                     'reason': 'Accepted content types:'
                                     })
    if isinstance(filename_or_handle, (str, unicode)) and \
            os.path.exists(filename_or_handle):  # it's a file name
        mediasource = gdata.MediaSource()
        mediasource.setFile(filename_or_handle, content_type)
    elif hasattr(filename_or_handle, 'read'):  # it's a file-like resource
        if hasattr(filename_or_handle, 'seek'):
            filename_or_handle.seek(0)  # rewind pointer to the start of the file
        # gdata.MediaSource needs the content length, so read the whole image
        file_handle = StringIO.StringIO(filename_or_handle.read())
        name = 'image'
        if hasattr(filename_or_handle, 'name'):
            name = filename_or_handle.name
        mediasource = gdata.MediaSource(file_handle, content_type,
                                        content_length=file_handle.len, file_name=name)
    else:  # filename_or_handle is not valid
        raise GooglePhotosException({'status': GPHOTOS_INVALID_ARGUMENT,
                                     'body': '`filename_or_handle` must be a path name or a file-like object',
                                     'reason': 'Found %s, not path name or object with a .read() method' % \
                                               type(filename_or_handle)
                                     })

    if isinstance(album_or_uri, (str, unicode)):  # it's a uri
        feed_uri = album_or_uri
    elif hasattr(album_or_uri, 'GetFeedLink'):  # it's a AlbumFeed object
        feed_uri = album_or_uri.GetFeedLink().href

    try:
        return self.Post(video, uri=feed_uri, media_source=mediasource,
                         converter=None)
    except gdata.service.RequestError, e:
        raise GooglePhotosException(e.args[0])


gdata.photos.service.PhotosService.InsertVideo = InsertVideo

# Class to store details of an album
class Albums:
    def __init__(self, rootDirs, albumNaming, excludes, replace, namingextract):
        self.rootDirs = rootDirs
        self.albums = self.scanFileSystem(albumNaming, excludes, replace, namingextract)

    # walk the directory tree populating the list of files we have locally
    # @print_timing
    def scanFileSystem(self, albumNaming, excludes, replace, namingextract):
        fileAlbums = {}
        for rootDir in self.rootDirs:
            for dirName, subdirList, fileList in os.walk(rootDir):
                subdirList[:] = [d for d in subdirList if not re.match(excludes, os.path.join(dirName, d))]
                albumName = convertDirToAlbum(albumNaming, rootDir, dirName, replace, namingextract)
                # have we already seen this album? If so append our path to it's list
                if albumName in fileAlbums:
                    album = fileAlbums[albumName]
                    thisRoot = album.suggestNewRoot(dirName)
                else:
                    # create a new album
                    thisRoot = dirName
                    album = AlbumEntry(dirName, albumName)
                    fileAlbums[albumName] = album
                # now iterate it's files to add them to our list
                for fname in fileList:
                    fullFilename = os.path.join(dirName, fname)
                    if not re.match(excludes, fullFilename):
                        # figure out the filename relative to the root dir of the album (to ensure uniqeness)
                        relFileName = re.sub("^/", "", fullFilename[len(thisRoot):])
                        fileEntry = FileEntry(relFileName, fullFilename, None, True, album)
                        album.entries[relFileName] = fileEntry
        if verbose:
            print ("Found " + str(len(fileAlbums)) + " albums on the filesystem")
        return fileAlbums;

    def deleteEmptyWebAlbums(self, owner):
        webAlbums = gd_client.GetUserFeed(user=owner)
        for webAlbum in webAlbums.entry:
            if int(webAlbum.numphotos.text) == 0:
		if not webAlbum.title.text in immutableFolders:
                	print "Deleting empty album %s" % webAlbum.title.text
                	gd_client.Delete(webAlbum)
                	# @print_timing

    def scanWebAlbums(self, owner, deletedups, server_excludes):
        # walk the web album finding albums there
        webAlbums = gd_client.GetUserFeed(user=owner)
        for webAlbum in webAlbums.entry:
            webAlbumTitle = Albums.flatten(webAlbum.title.text)
            if re.match(server_excludes, webAlbumTitle):
                if verbose:
                    print ('Skipping (because matches server exclude) web-album %s (containing %s files)' % (
                        webAlbum.title.text, webAlbum.numphotos.text))
            else:
                if verbose:
                    print (
                        'Scanning web-album %s (containing %s files)' % (webAlbum.title.text, webAlbum.numphotos.text))
                # print "Album %s is %s in %s" % (webAlbumTitle, webAlbumTitle in self.albums,	",".join(self.albums))
                if webAlbumTitle in self.albums:
                    foundAlbum = self.albums[webAlbumTitle]
                    self.scanWebPhotos(foundAlbum, webAlbum, deletedups)
                else:
                    album = AlbumEntry(os.path.join(self.rootDirs[0], webAlbum.title.text), webAlbum.title.text)
                    self.albums[webAlbum.title.text] = album
                    self.scanWebPhotos(album, webAlbum, deletedups)


    # @print_timing
    def scanWebPhotos(self, foundAlbum, webAlbum, deletedups):
        # bit of a hack, but can't see anything in api to do it.
        photos = repeat(lambda: gd_client.GetFeed(webAlbum.GetPhotosUri() + "&imgmax=d"),
                        "list photos in album %s" % foundAlbum.albumName, True)
        webAlbum = WebAlbum(webAlbum, int(photos.total_results.text))
        foundAlbum.webAlbum.append(webAlbum)
        for photo in photos.entry:
            if photo.title.text == None:
                photoTitle = ""
            else:
                photoTitle = urllib.unquote(photo.title.text)

            if photoTitle in foundAlbum.entries:
                entry = foundAlbum.entries[photoTitle]
                if entry.isWeb():
                    if (deletedups):
                        print "Deleted dupe of %s on server" % photoTitle
                        repeat(lambda: gd_client.Delete(photo), "deleting dupe %s" % photoTitle, False)
                    else:
                        print "WARNING: More than one copy of %s - ignoring" % photoTitle
                else:
                    entry.setWebReference(photo)
                    # print photo.exif.time
            else:
                fileEntry = FileEntry(photoTitle, None, photo, False, foundAlbum)
                foundAlbum.entries[photoTitle] = fileEntry

    # @print_timing
    def uploadMissingAlbumsAndFiles(self, compareattributes, mode, test, allowDelete):
        size = 0
        for album in self.albums.itervalues():
            size += len(album.entries)
        count = 0
        actionCounts = {}
        for action in Actions:
            actionCounts[action] = 0
        for album in self.albums.itervalues():
            for file in album.entries.itervalues():
                changed = file.changed(compareattributes)
                if verbose:
                    print ("%s (%s) #%s/%s - %s" % (mode[changed], changed, str(count), str(size), file.getFullName()))
                if not test:
                    if mode[changed] == Actions.DELETE_LOCAL and not allowDelete[0]:
                        print (
                            "Not deleteing local file %s because permissions not granted using allowDelete" % file.getFullName())
                    else:
                        if mode[changed] == Actions.DELETE_REMOTE and not allowDelete[1]:
                            print (
                                "Not deleteing remote file %s because permissions not granted using allowDelete" % file.getFullName())
                        else:
                            repeat(lambda: getattr(file, mode[changed].lower())(changed),
                                   "%s on %s identified as %s" % (mode[changed], file.getFullName(), changed), False)
                actionCounts[mode[changed]] += 1
                count += 1
            album.writeDate()
        print("Finished transferring files. Total files found %s, composed of %s" % (count, str(actionCounts)))

    @staticmethod
    def createAlbumName(name, index):
        if index == 0:
            return name
        else:
            return "%s #%s" % (name, index + 1)

    @staticmethod
    def flatten(name):
        return re.sub("#[0-9]*$", "", name).rstrip()


class AlbumEntry:
    def __init__(self, fileName, albumName):
        self.paths = [fileName]
        self.rootPath = fileName
        self.albumName = albumName
        self.entries = {}
        self.webAlbum = []
        self.webAlbumIndex = 0
        self.earliestDate = None

    def considerEarliestDate(self, exif):
        if exif != None and exif.time != None and noupdatealbummetadata == False:
            date = exif.time.text
            if self.earliestDate == None or date < self.earliestDate:
                self.earliestDate = date

    def writeDate(self):
        if self.earliestDate != None and noupdatealbummetadata == False:
            if verbose:
                print "Attempting to write date (" + self.earliestDate + ") to album " + self.albumName
            for a in self.webAlbum:
                album = a.getEditObject()
                album.timestamp = gdata.photos.Timestamp(text=self.earliestDate)
                edit_link = album.GetEditLink()
                if edit_link == None:
                    print "Warning: Null edit link from " + a.albumTitle + " so skipping metadata update"
                else:
                    repeat(lambda: gd_client.Put(album, edit_link.href, converter=gdata.photos.AlbumEntryFromString),
                           "Update album metadata for " + a.albumTitle, False)
        else:
            print "Not Attempting to write date to album " + self.albumName

    def __str__(self):
        return (self.getAlbumName() + " under " + self.rootPath + " " + str(len(self.entries)) + " entries " + \
                ["exists", "doesn't exist"][not self.webAlbum] + " online")

    def getAlbumName(self):
        return self.albumName

    def getPathsAsString(self):
        return ",".join(self.paths)

    def suggestNewRoot(self, name):
        for path in self.paths:
            if name.startswith(path):
                return path
        self.paths.append(name)
        return name


# Class to store web album details

class WebAlbum:
    def __init__(self, album, numberFiles):
        self.albumUri = album.GetPhotosUri()
        self.albumTitle = album.title.text
        self.numberFiles = numberFiles
        self.albumid = album.id.text

    def getEditObject(self):
        # print "Getting id "+self.albumid +" = "+gd_client.GetEntry(self.albumid)
        return gd_client.GetEntry(self.albumid)


# Class to store details of an individual file

class FileEntry:
    def __init__(self, name, path, webReference, isLocal, album):
        self.name = name
        if path:
            self.path = path
            self.type = mimetypes.guess_type(path)[0]
        else:
            self.path = os.path.join(album.rootPath, name)
            self.type = None
        self.isLocal = isLocal
        self.localHash = None
        self.remoteHash = None
        self.remoteDate = None
        self.remoteTimestamp = None
        self.remoteSize = None
        self.album = album
        self.setWebReference(webReference)

    def setWebReference(self, webReference):
        if webReference:
            for content in webReference.media.content:
                # If we haven't found a type yet, or prioritise video type
                if not self.type or (content.medium == 'video'):
                    self.type = content.type

            self.gphoto_id = webReference.gphoto_id.text
            self.albumid = webReference.albumid.text
            self.webUrl = webReference.content.src
            
            #if video overwrite webUrl : get last (higher resolution) media.content entry url
            if webReference.media.content:
                highRescontent = webReference.media.content[-1]
                if highRescontent.type.startswith('video'):
                    if highRescontent.url:
                        self.webUrl = highRescontent.url
            
            self.remoteHash = webReference.checksum.text
            self.remoteDate = calendar.timegm(
                time.strptime(re.sub("\.[0-9]{3}Z$", ".000 UTC", webReference.updated.text),
                              '%Y-%m-%dT%H:%M:%S.000 %Z'))
            self.remoteTimestamp = time.mktime(webReference.timestamp.datetime().timetuple())
            self.remoteSize = int(webReference.size.text)
        else:
            self.webUrl = None

    def getEditObject(self):
        if self.gphoto_id:
            photo = gd_client.GetFeed(
                '/data/feed/api/user/%s/albumid/%s/photoid/%s' % ("default", self.albumid, self.gphoto_id))
            return photo
        # FIXME throw exception
        return None

    def getFullName(self):
        return self.album.getAlbumName() + " " + self.name

    def getLocalHash(self):
        if not (self.localHash):
            md5 = hashlib.md5()
            with open(self.path, 'rb') as f:
                for chunk in iter(lambda: f.read(128 * md5.block_size), b''):
                    md5.update(chunk)
            self.localHash = md5.hexdigest()
        return self.localHash

    def getLocalDate(self):
        return os.path.getmtime(self.path)

    def getLocalSize(self):
        return os.path.getsize(self.path)

    def changed(self, compareattributes):
        if self.isLocal:
            if self.isWeb():
                # filesize (2), date (1),  hash (4)
                if compareattributes & 1:
                    # print "%s: remote=%s and local=%s" % (self.getFullName(), time.gmtime(self.remoteDate), time.gmtime(self.getLocalDate()))
                    if self.remoteDate < self.getLocalDate() + 60:
                        return Comparisons.REMOTE_OLDER
                if compareattributes & 2:
                    if verbose:
                        print "%s: remote size=%s and local=%s" % (
                            self.getFullName(), self.remoteSize, self.getLocalSize())
                    if self.remoteSize != self.getLocalSize():
                        return Comparisons.DIFFERENT
                if compareattributes & 4:
                    if self.remoteHash:
                        if self.remoteHash != self.getLocalHash():
                            return Comparisons.DIFFERENT
                    else:
                        return Comparisons.UNKNOWN
                return Comparisons.SAME
            else:
                return Comparisons.LOCAL_ONLY
        else:
            return Comparisons.REMOTE_ONLY

    def isWeb(self):
        return self.webUrl != None

    # UPLOAD_LOCAL', 'DELETE_LOCAL', 'SILENT', 'REPORT', 'DOWNLOAD_REMOTE', 'DELETE_REMOTE', 'TAG_REMOTE', 'REPLACE_REMOTE_WITH_LOCAL', 'UPDATE_REMOTE_METADATA'
    def delete_local(self, event):
        os.remove(self.path)

    def silent(self, event):
        None

    def report(self, event):
        print ("Identified %s as %s - taking no action" % (self.name, event))

    def tag_remote(self, event):
        print ("Not implemented tag")

    def replace_remote_with_local(self, event):
        self.delete_remote(event)
        self.upload_local(event)

    def update_remote_metadata(self, event):
        entry = gd_client.GetEntry(self.getEditObject().GetEditLink().href)
        self.album.considerEarliestDate(entry.exif)
        self.addMetadata(entry)
        self.setWebReference(gd_client.UpdatePhotoMetadata(entry))

    def download_remote(self, event):
        if self.type not in chosenFormats:
            print ("Skipped %s (because can't download file of type %s)." % (self.path, self.type))
        elif dateLimit is not None and self.remoteTimestamp < dateLimit:
            print ("Skipped %s (because remote album pre %s)." % (self.path, time.asctime(dateLimit)))
        else:
            url = self.webUrl
            path = os.path.split(self.path)[0]
            if not os.path.exists(path):
                os.makedirs(path)
            urllib.urlretrieve(url, self.path)
            os.utime(path, (int(self.remoteDate), int(self.remoteDate)))

    def delete_remote(self, event):
        gd_client.Delete(self.getEditObject())
        print ("Deleted %s" % self.getFullName())

    def upload_local(self, event):
        if self.type in chosenFormats:
            while (self.album.webAlbumIndex < len(self.album.webAlbum) and self.album.webAlbum[
                self.album.webAlbumIndex].numberFiles >= 999):
                self.album.webAlbumIndex = self.album.webAlbumIndex + 1
            if self.album.webAlbumIndex >= len(self.album.webAlbum):
                googleWebAlbum = gd_client.InsertAlbum(
                    title=Albums.createAlbumName(self.album.getAlbumName(), self.album.webAlbumIndex), access='private',
                    summary='synced from ' + self.album.rootPath + ' using github.com/leocrawford/picasawebsync')
                subAlbum = WebAlbum(googleWebAlbum, 0)
                self.album.webAlbum.append(subAlbum)
                if verbose:
                    print ('Created album %s to sync %s' % (subAlbum.albumTitle, self.album.rootPath))
            else:
                subAlbum = self.album.webAlbum[self.album.webAlbumIndex]
            if self.type in supportedImageFormats:
                photo = self.upload_local_img(subAlbum)
            if self.type in supportedVideoFormats:
                if self.getLocalSize() > 1073741824:
                    print ("Not uploading %s because it exceeds maximum file size" % self.path)
                else:
                    photo = self.upload_local_video(subAlbum)
        else:
            print ("Skipped %s (because can't upload file of type %s)." % (self.path, self.type))

    def upload_local_img(self, subAlbum):
        name = urllib.quote(self.name, '')
        metadata = gdata.photos.PhotoEntry()
        metadata.title = atom.Title(text=name)  # have to quote as certain charecters, e.g. / seem to break it
        self.addMetadata(metadata)
        shrinkFile = shrinkIfNeeded(self.path)
        currentFile = self.path
        if (shrinkFile is not None):
            currentFile = shrinkFile
        photo = gd_client.InsertPhoto(subAlbum.albumUri, metadata, currentFile, self.type)
        if (shrinkFile is not None):
            os.remove(shrinkFile)
        self.album.considerEarliestDate(photo.exif)
        subAlbum.numberFiles = subAlbum.numberFiles + 1
        return photo

    def upload_local_video(self, subAlbum):
        name = urllib.quote(self.name, '')
        metadata = gdata.photos.VideoEntry()
        metadata.title = atom.Title(text=name)  # have to quote as certain charecters, e.g. / seem to break it
        self.addMetadata(metadata)
        photo = gd_client.InsertVideo(subAlbum.albumUri, metadata, self.path, self.type)
        subAlbum.numberFiles = subAlbum.numberFiles + 1
        return photo

    def addMetadata(self, metadata):
        metadata.summary = atom.Summary(text=os.path.relpath(self.path, self.album.rootPath), summary_type='text')
        metadata.checksum = gdata.photos.Checksum(text=self.getLocalHash())
        if verbose and (metadata == None):
            print "Warning: " + self.name + " does not have a date set"


# Method to translate directory name to an album name	

def convertDirToAlbum(formElements, root, name, replace, namingextract):
    if root == name:
        return "Home"
    nameElements = re.split("/", re.sub("^/", "", name[len(root):]))
    which = min(len(formElements), len(nameElements))
    work = formElements[which - 1].format(*nameElements)
    # apply naming extraction if provided
    if namingextract:
        nePattern = namingextract.split('|')
        work = re.sub(nePattern[0], nePattern[1], work)

    # apply replacement pattern if provided
    if replace:
        rePattern = replace.split('|')
        work = re.sub(rePattern[0], rePattern[1], work)

    return work


supportedImageFormats = frozenset(["image/bmp", "image/gif", "image/jpeg", "image/png"])
# supportedImageFormats = frozenset(["image/jpeg", "image/png"])
supportedVideoFormats = frozenset(
    ["video/3gpp", "video/avi", "video/quicktime", "video/mp4", "video/mpeg", "video/mpeg4", "video/msvideo", "video/x-ms-asf", "video/x-ms-wmv", "video/x-msvideo", "video/x-matroska"])
immutableFolders = frozenset(["Instant Upload","Auto-Backup","Auto Backup"])


class Enum(set):
    def __getattr__(self, name):
        if name in self:
            return name
        raise AttributeError


Comparisons = Enum(['REMOTE_OLDER', 'DIFFERENT', 'SAME', 'UNKNOWN', 'LOCAL_ONLY', 'REMOTE_ONLY'])
Actions = Enum(['UPLOAD_LOCAL', 'DELETE_LOCAL', 'SILENT', 'REPORT', 'DOWNLOAD_REMOTE', 'DELETE_REMOTE', 'TAG_REMOTE',
                'REPLACE_REMOTE_WITH_LOCAL', 'UPDATE_REMOTE_METADATA'])
UploadOnlyActions = {
    Comparisons.REMOTE_OLDER: Actions.REPLACE_REMOTE_WITH_LOCAL,
    Comparisons.DIFFERENT: Actions.REPORT,
    Comparisons.SAME: Actions.SILENT,
    Comparisons.UNKNOWN: Actions.REPORT,
    Comparisons.LOCAL_ONLY: Actions.UPLOAD_LOCAL,
    Comparisons.REMOTE_ONLY: Actions.REPORT}
DownloadOnlyActions = {
    Comparisons.REMOTE_OLDER: Actions.REPORT,
    Comparisons.DIFFERENT: Actions.DOWNLOAD_REMOTE,
    Comparisons.SAME: Actions.SILENT,
    Comparisons.UNKNOWN: Actions.REPORT,
    Comparisons.LOCAL_ONLY: Actions.REPORT,
    Comparisons.REMOTE_ONLY: Actions.DOWNLOAD_REMOTE}
PassiveActions = {
    Comparisons.REMOTE_OLDER: Actions.REPORT,
    Comparisons.DIFFERENT: Actions.REPORT,
    Comparisons.SAME: Actions.SILENT,
    Comparisons.UNKNOWN: Actions.REPORT,
    Comparisons.LOCAL_ONLY: Actions.REPORT,
    Comparisons.REMOTE_ONLY: Actions.REPORT}
RepairActions = {
    Comparisons.REMOTE_OLDER: Actions.REPLACE_REMOTE_WITH_LOCAL,
    Comparisons.DIFFERENT: Actions.REPLACE_REMOTE_WITH_LOCAL,
    Comparisons.SAME: Actions.SILENT,
    Comparisons.UNKNOWN: Actions.UPDATE_REMOTE_METADATA,
    Comparisons.LOCAL_ONLY: Actions.UPLOAD_LOCAL,
    Comparisons.REMOTE_ONLY: Actions.DELETE_REMOTE}
SyncActions = {
    Comparisons.REMOTE_OLDER: Actions.REPLACE_REMOTE_WITH_LOCAL,
    Comparisons.DIFFERENT: Actions.REPORT,
    Comparisons.SAME: Actions.SILENT,
    Comparisons.UNKNOWN: Actions.REPORT,
    Comparisons.LOCAL_ONLY: Actions.UPLOAD_LOCAL,
    Comparisons.REMOTE_ONLY: Actions.DOWNLOAD_REMOTE}
SyncUploadActions = {
    Comparisons.REMOTE_OLDER: Actions.REPLACE_REMOTE_WITH_LOCAL,
    Comparisons.DIFFERENT: Actions.REPLACE_REMOTE_WITH_LOCAL,
    Comparisons.SAME: Actions.SILENT,
    Comparisons.UNKNOWN: Actions.REPLACE_REMOTE_WITH_LOCAL,
    Comparisons.LOCAL_ONLY: Actions.UPLOAD_LOCAL,
    Comparisons.REMOTE_ONLY: Actions.DELETE_REMOTE}

modes = {'upload': UploadOnlyActions, 'download': DownloadOnlyActions, 'report': PassiveActions,
         'repairUpload': RepairActions, 'sync': SyncActions, 'syncUpload': SyncUploadActions}
formats = {'photo': supportedImageFormats, 'video': supportedVideoFormats,
           'both': supportedImageFormats.union(supportedVideoFormats)}
allowDeleteOptions = {'neither': (False, False), 'both': (True, True), 'local': (True, False), 'remote': (False, True)}


def convertAllowDelete(string):
    return allowDeleteOptions[string]


def convertMode(string):
    return modes[string]


def convertFormat(string):
	return formats[string]

def convertDate(string):
    return time.strptime(string, '%Y-%m-%d')

def repeat(function,  description, onFailRethrow):
	exc_info = None
	for attempt in range(3):
		try:
			if verbose and (attempt > 0):
				print ("Trying %s attempt %s" % (description, attempt) )	
			return function()
		except Exception,  e:
			if exc_info == None:
				exc_info = e
			# FIXME - to try and stop 403 token expired
			time.sleep(6)
			# this should no longer be needed			
			# gd_client=oauthLogin() 

			continue
		else:
			break
	else:
		print ("WARNING: Failed to %s. This was due to %s" % (description, exc_info))
		if onFailRethrow:
			raise exc_info
			
def oauthLogin():
	# using http://stackoverflow.com/questions/20248555/list-of-spreadsheets-gdata-oauth2/29157967#29157967 (thanks)
	from oauth2client.file import Storage

	filename = os.path.join(os.path.expanduser('~'), ".picasawebsync")
	storage = Storage(filename)
	credentials = storage.get()
	if credentials is None or credentials.invalid:	
		flow = client.flow_from_clientsecrets('client_secrets.json',scope='https://picasaweb.google.com/data/',redirect_uri='urn:ietf:wg:oauth:2.0:oob')	
		auth_uri = flow.step1_get_authorize_url()	
		print 'Authorization URL: %s' % auth_uri
		auth_code = raw_input('Enter the auth code: ')
		credentials = flow.step2_exchange(auth_code)
		storage.put(credentials)
	# if credentials.access_token_expired:		
	
	return refreshCreds(credentials,0)


def refreshCreds(credentials,sleep):
        global gd_client	
        time.sleep(sleep)
	credentials.refresh(httplib2.Http())	

	now = datetime.utcnow() 
 	expires = credentials.token_expiry
	expires_seconds = (expires-now).seconds 	
	# print ("Expires %s from %s = %s" % (expires,now,expires_seconds) )

	gd_client = gdata.photos.service.PhotosService(email='default',additional_headers={'Authorization' : 'Bearer %s' % credentials.access_token})
	
	d = threading.Thread(name='refreshCreds', target=refreshCreds, args=(credentials,expires_seconds - 10) )
	d.setDaemon(True)
	d.start()
	return gd_client
	


# start of the program

defaultNamingFormat = ["{0}", "{1} ({0})"]

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--directory", nargs='+',
                    help="The local directories. The first of these will be used for any downloaded items")
parser.add_argument("-n", "--naming", default=defaultNamingFormat, nargs='+',
                    help="Expression to convert directory names to web album names. Formed as a ~ seperated list of substitution strings, "
                         "so if a sub directory is in the root scanning directory then the first slement will be used, if there is a directory between them the second, etc. If the directory path is longer than the "
                         "list then the last element is used (and thus the path is flattened). Default is \"%s\"" % defaultNamingFormat)
# parser.add_argument("-m", "--metadatalevel", type=convertImpactLevel, help="metadata level %s" % list(activityLevels),  default="upload")
parser.add_argument("--namingextract", default=False,
                    help="Naming extraction rules. It applies to the name computed according to naming options."
                         "Search capturing pattern is seperated by a | from formatting expression (ex: '([0-9]{4})[0-9]*-(.*)|\2 (\2)'")
parser.add_argument("-c", "--compareattributes", type=int,
                    help="set of flags to indicate whether to use date (1), filesize (2), hash (4) in addition to filename. "
                         "These are applied in order from left to right with a difference returning immediately and a similarity passing on to the next check."
                         "They work like chmod values, so add the values in brackets to switch on a check. Date uses a 60 second margin (to allow for different time stamp"
                         "between google and your local machine, and can only identify a locally modified file not a remotely modified one. Filesize and hash are used by default",
                    default=3)
parser.add_argument("-v", "--verbose", default=False, action='store_true', help="Increase verbosity")
parser.add_argument("-t", "--test", default=False, action='store_true',
                    help="Don't actually run activities, but report what you would have done (you may want to enable verbose)")
parser.add_argument("-m", "--mode", type=convertMode,
                    help="The mode is a preset set of actions to execute in different circumstances, e.g. upload, download, sync, etc. The full set of optoins is %s. "
                         "The default is upload. Look at the github page for full details of what each action does" % list(
                        modes), default="upload")
parser.add_argument("-dd", "--deletedups", default=False, action='store_true', help="Delete any remote side duplicates")
parser.add_argument("-f", "--format", type=convertFormat, default="photo", help="Upload photos, videos or both")
parser.add_argument("-s", "--skip", nargs='*', default=[],
                    help="Skip (local) files or folders using a list of glob expressions.")
parser.add_argument("--skipserver", nargs='*', default=[],
                    help="Skip (remote) files or folders using a list of glob expressions.")
parser.add_argument("--shrink", default=False, action='store_true',
                    help="Shrink to max free google size (may cause problems with -c2 and maybe even -c1. Please report.")
parser.add_argument("--purge", default=False, action='store_true', help="Purge empty web filders")
parser.add_argument("--noupdatealbummetadata", default=False, action='store_true',
                    help="Disable the updating of album metadata")
parser.add_argument("--allowDelete", type=convertAllowDelete, default="neither",
                    help="Are we allowed to do delete operations: %s" % list(allowDeleteOptions))
parser.add_argument("-r", "--replace", default=False,
                    help="Replacement pattern. Search string is seperated by a pipe from replace string (ex: '-| '")
parser.add_argument("-o", "--owner", default="default",
                    help="The username of the user whos albums to sync (leave blank for your own)")
parser.add_argument("--dateLimit", type=convertDate, help="A date limit, before which albums are ignored.")
for comparison in Comparisons:
    parser.add_argument("--override:%s" % comparison, default=None,
                        help="Override the action for %s from the list of %s" % (comparison, ",".join(list(Actions))))
args = parser.parse_args()

chosenFormats = args.format
dateLimit = args.dateLimit

gd_client = oauthLogin()
verbose = args.verbose
rootDirs = args.directory  # set the directory you want to start from

albumNaming = args.naming
mode = args.mode
noupdatealbummetadata = args.noupdatealbummetadata
for comparison in Comparisons:
    r = getattr(args, "override:%s" % comparison, None)
    if r:
        mode[comparison] = r

excludes = r'|'.join([fnmatch.translate(x) for x in args.skip]) or r'$.'
server_excludes = r'|'.join([fnmatch.translate(x) for x in args.skipserver]) or r'$.'

print ("Excluding %s on client and %s on server" % (excludes, server_excludes))

albums = Albums(rootDirs, albumNaming, excludes, args.replace, args.namingextract)
albums.scanWebAlbums(args.owner, args.deletedups, server_excludes)
albums.uploadMissingAlbumsAndFiles(args.compareattributes, mode, args.test, args.allowDelete)

if args.purge:
    albums.deleteEmptyWebAlbums(args.owner)

