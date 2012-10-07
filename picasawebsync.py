#!/usr/bin/python

from gdata.photos.service import  *
import gdata.media
import gdata.geo
import os
import re
import pprint
import sys
import argparse
import mimetypes
import hashlib
import urllib
import time
import datetime
import urllib
import json

# Class to store details of an album

supportedImageFormats = frozenset(["image/bmp", "image/gif",  "image/jpeg",  "image/png"])

class Enum(set):
    def __getattr__(self, name):
        if name in self:
            return name
        raise AttributeError
    
Comparisons = Enum(['REMOTE_OLDER', 'DIFFERENT', 'SAME', 'UNKNOWN', 'LOCAL_ONLY', 'REMOTE_ONLY'])   
Actions = Enum(['UPLOAD_LOCAL', 'DELETE_LOCAL', 'SILENT', 'REPORT', 'DOWNLOAD_REMOTE', 'DELETE_REMOTE', 'TAG_REMOTE', 'REPLACE_REMOTE_WITH_LOCAL', 'UPDATE_REMOTE_METADATA'])
UploadOnlyActions = {
        Comparisons.REMOTE_OLDER:Actions.REPLACE_REMOTE_WITH_LOCAL, 
        Comparisons.DIFFERENT:Actions.REPORT, 
        Comparisons.SAME:Actions.UPDATE_REMOTE_METADATA,  #SILENT, 
        Comparisons.UNKNOWN:Actions.REPORT, 
        Comparisons.LOCAL_ONLY:Actions.UPLOAD_LOCAL, 
        Comparisons.REMOTE_ONLY:Actions.REPORT}
PassiveActions = {
        Comparisons.REMOTE_OLDER:Actions.REPORT, 
        Comparisons.DIFFERENT:Actions.REPORT, 
        Comparisons.SAME:Actions.SILENT, 
        Comparisons.UNKNOWN:Actions.REPORT, 
        Comparisons.LOCAL_ONLY:Actions.REPORT, 
        Comparisons.REMOTE_ONLY:Actions.REPORT}        
RepairActions= {
        Comparisons.REMOTE_OLDER:Actions.REPLACE_REMOTE_WITH_LOCAL, 
        Comparisons.DIFFERENT:Actions.REPLACE_REMOTE_WITH_LOCAL, 
        Comparisons.SAME:Actions.UPDATE_REMOTE_METADATA,  #SILENT, 
        Comparisons.UNKNOWN:Actions.REPORT, 
        Comparisons.LOCAL_ONLY:Actions.UPLOAD_LOCAL, 
        Comparisons.REMOTE_ONLY:Actions.REPORT}
modes = {'upload':UploadOnlyActions, 'download':PassiveActions, 'report':PassiveActions, 'sync':PassiveActions,  'repairUpload':RepairActions}
def convertMode(string):
    return modes[string]

def repeat(function,  description):
    for attempt in range(3):
        try:
            if verbose and (attempt > 0):
                print ("Trying %s attempt %s" % (description, attempt) )    
            return function()
        except:
            continue
        else:
            break
    else:
        print ("Failed 3 times")
        exit(-1)      


class Albums:
    def __init__(self, rootDirs, albumNaming):
        self.albums = Albums.scanFileSystem(rootDirs, albumNaming)
        self.rootDirs = rootDirs
    # walk the directory tree populating the list of files we have locally
    @staticmethod
    def scanFileSystem(rootDirs, albumNaming):
        fileAlbums = {}
        for rootDir in rootDirs:
            for dirName,subdirList,fileList in os.walk( rootDir ) :
                albumName = convertDirToAlbum(albumNaming, rootDir,  dirName)
                # have we already seen this album? If so append our path to it's list
                if albumName in fileAlbums:
                    album = fileAlbums[album.getAlbumName()]
                    album.paths.append(dirName)
                else:
                    # create a new album
                    album = AlbumEntry(dirName,  albumName)
                    fileAlbums[album.getAlbumName()] = album
                # now iterate it's files to add them to our list
                for fname in fileList :
                    fullFilename = os.path.join(dirName, fname)
                    # figure out the filename relative to the root dir of the album (to ensure uniqeness) 
                    relFileName = re.sub("^/","", fullFilename[len(album.rootPath):])
                    fileEntry = FileEntry(relFileName, fullFilename,  None, True, album)
                    album.entries[relFileName] = fileEntry
        print ("Found "+str(len(fileAlbums))+" albums on the filesystem")
        return fileAlbums;
    def scanWebAlbums(self):
        # walk the web album finding albums there
        webAlbums = gd_client.GetUserFeed()
        for webAlbum in webAlbums.entry:
            webAlbumTitle = Albums.flatten(webAlbum.title.text)
            if webAlbumTitle in self.albums:
                foundAlbum = self.albums[webAlbumTitle]
                self.scanWebPhotos(foundAlbum, webAlbum)
            else:
                # FIXME
                album = AlbumEntry(os.path.join(rootDir, "downloaded", webAlbum.title.text),  webAlbum.title.text)
                self.albums[webAlbum.title.text] = album
                self.scanWebPhotos(album, webAlbum)
            if verbose:
                print ('Scanned web-album %s (containing %s files)' % (webAlbum.title.text, webAlbum.numphotos.text))
    def scanWebPhotos(self, foundAlbum, webAlbum):
        photos = repeat(lambda: gd_client.GetFeed(webAlbum.GetPhotosUri()), "list photos in album %s" % foundAlbum.albumName)
        foundAlbum.webAlbum.append(WebAlbum(webAlbum, int(photos.total_results.text)))
        for photo in photos.entry:
            photoTitle=urllib.unquote(photo.title.text)
            if photoTitle in foundAlbum.entries: 
                entry = foundAlbum.entries[photoTitle]
                entry.webReference = photo.content.src
                entry.remoteHash = photo.checksum.text
                entry.remoteDate = time.mktime(time.strptime( re.sub("\.[0-9]{3}Z$",".000 UTC",photo.updated.text),'%Y-%m-%dT%H:%M:%S.000 %Z'))
                entry.remoteSize = int(photo.size.text)
                # or photo.exif.time
            else:
                fileEntry = FileEntry(photoTitle, None,  photo, False, foundAlbum)
                foundAlbum.entries[photoTitle] = fileEntry
    def uploadMissingAlbumsAndFiles(self, compareattributes, mode, test):
        for album in self.albums.itervalues():
            for file in album.entries.itervalues():
                changed = file.changed(compareattributes)
                if verbose:
                    print ("%s: %s->%s" % (file.getFullName(), changed,  mode[changed]))
                if not test:
                    repeat(lambda: getattr(file, mode[changed].lower())(changed), "%s on %s identified as %s" % (mode[changed],  file.getFullName(), changed ))
    @staticmethod 
    def createAlbumName(name,  index):
        if index == 0:
            return name
        else:
            return "%s #%s" % (name, index)
    @staticmethod
    def flatten(name):
        return re.sub("#[0-9]*$","",name)
        

class AlbumEntry:
    def __init__(self, fileName,  albumName):
        self.paths = [fileName]
        self.rootPath= fileName
        self.albumName = albumName
        self.entries = {}
        self.webAlbum = []
        self.webAlbumIndex = 0
    def __str__(self):
        return (self.albumName+" starting at "+rootPath+" total "+str(len(self.entries))+" entries "+\
            ["exists","doesn't exist"][not self.webAlbum]+" online")
    def getAlbumName(self):
        if (len(self.albumName) > 0):
            return self.albumName
        else:
            return "Home"
    def getPathsAsString(self):
        return ",".join(self.paths)
    
# Class to store web album details

class WebAlbum:
    def __init__(self, album,  numberFiles):
        self.albumUri = album.GetPhotosUri()
        self.albumTitle = album.title.text
        self.numberFiles = numberFiles


# Class to store details of an individual file

class FileEntry:
    def __init__(self, name, path,  webReference,  isLocal,  album):
        self.name = name
        self.path=path
        self.isLocal=isLocal
        self.localHash=None
        self.remoteHash=None
        if webReference:
            self.webUrl=webReference.content.src
        else:
            self.webUrl = None
        self.remoteDate=None
        self.remoteSize=None
        self.album=album
    def getFullName(self):
        return self.album.getAlbumName()+" "+self.name
    def getLocalHash(self):
        if not(self.localHash):
            md5 = hashlib.md5()
            with open(self.path,'rb') as f: 
                for chunk in iter(lambda: f.read(128*md5.block_size), b''): 
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
                    if self.remoteDate < self.getLocalDate() + 60:
                        return Comparisons.REMOTE_OLDER              
                if compareattributes & 2: 
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
        print ("Not implemented delete")
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
        self.addMetadata(self.webUrl)
        self.webUrl = gd_client.UpdatePhotoMetadata(self.webUrl).content.src
    def download_remote(self, event):
        url = self.webUrl
        "Download the data at URL to the current directory."
        basename = url[url.rindex('/') + 1:]  # Figure out a good name for the downloaded file.
        print ("Downloading %s" % (basename,))
        urllib.urlretrieve(url, basename)
    def delete_remote(self, event):
        print ("Deleting %s" % (self.name))
        gd_client.Delete(self.webUrl)        
    def upload_local(self, event):
        while (self.album.webAlbumIndex<len(self.album.webAlbum) and self.album.webAlbum[self.album.webAlbumIndex].numberFiles >= 999):
            self.album.webAlbumIndex = self.album.webAlbumIndex + 1                        
        if self.album.webAlbumIndex>=len(self.album.webAlbum):
            subAlbum = WebAlbum(gd_client.InsertAlbum(title=Albums.createAlbumName(self.album.getAlbumName(), self.album.webAlbumIndex), access='private', summary='synced from '+self.album.rootPath), 0)
            self.album.webAlbum.append(subAlbum)
            print ('Created album %s to sync %s' % (subAlbum.albumTitle, self.album.rootPath))
        else:
            subAlbum = self.album.webAlbum[self.album.webAlbumIndex]
        photo = self.upload2(subAlbum)    
    def upload2(self,  subAlbum):
        try:
            mimeType = mimetypes.guess_type(self.path)[0]
            if mimeType in supportedImageFormats:
                name = urllib.quote_plus(self.name)
                print ("Uploading %s (as %s).." % (self.name, name))
                metadata = gdata.photos.PhotoEntry()
                metadata.title=atom.Title(text=name) # have to quote as certain charecters, e.g. / seem to break it
                self.addMetadata(metadata)
                photo = gd_client.InsertPhoto(subAlbum.albumUri, metadata, self.path, mimeType)
                subAlbum.numberFiles = subAlbum.numberFiles + 1
                return photo
            else:
                print ("Skipped %s (because can't upload file of type %s)." % (self.path, mimeType))
        except GooglePhotosException as detail:
            print ("Skipping upload of %s due to exception %s" % (self.path, detail) )
    def addMetadata(self, metadata):
            metadata.summary = atom.Summary(text='synced from '+self.path, summary_type='text')
            metadata.checksum= gdata.photos.Checksum(text=self.getLocalHash())
    
# Method to translate directory name to an album name   
    
def convertDirToAlbum(form,  root,  name):
    formElements = re.split("~", form)
    nameElements = re.split("/", re.sub("^/","",name[len(root):]))
    which = min(len(formElements), len(nameElements))
    work = formElements[which-1].format(*nameElements)
    return work

# start of the program

defaultNamingFormat="{0}~{1} ({0})"

parser = argparse.ArgumentParser()
parser.add_argument("-u","--username", help="Your picassaweb username")
parser.add_argument("-p","--password", help="Your picassaweb password")
parser.add_argument("-d","--directory",  nargs='+',help="The local directories. The first of these will be used for any downloaded items")
parser.add_argument("-n","--naming", default=defaultNamingFormat,  help="Expression to convert directory names to web album names. Formed as a ~ seperated list of substitution strings, "
"so if a sub directory is in the root scanning directory then the first slement will be used, if there is a directory between them the second, etc. If the directory path is longer than the "
"list then the last element is used (and thus the path is flattened). Default is \"%s\"" % defaultNamingFormat)
# parser.add_argument("-m", "--metadatalevel", type=convertImpactLevel, help="metadata level %s" % list(activityLevels),  default="upload")
parser.add_argument("-c", "--compareattributes", type=int, help="set of flags to indicate whether to use date (1), filesize (2), hash (4) in addition to filename. "
"These are applied in order from left to right with a difference returning immediately and a similarity passing on to the next check."
"They work like chmod values, so add the values in brackets to switch on a check. Date uses a 60 second margin (to allow for different time stamp"
"between google and your local machine, and can only identify a locally modified file not a remotely modified one. Filesize and hash are sued by default",  default=5)
parser.add_argument("-v","--verbose", default=False,  action='store_true',  help="Increase verbosity")
parser.add_argument("-t","--test", default=False,  action='store_true',  help="Don't actually run activities, but report what you would have done (you may want to enable verbose)")
parser.add_argument("-m","--mode", type=convertMode, help="The mode is a preset set of actions to execute in different circumstances, e.g. upload, download, sync, etc. The full set of optoins is %s. "
"The default is upload. The full set of actions is:\n%s" % (list(modes), json.dumps(modes)),  default="upload")
args = parser.parse_args()


gd_client = gdata.photos.service.PhotosService()
gd_client.email = args.username # Set your Picasaweb e-mail address...
gd_client.password = args.password 
gd_client.source = 'api-sample-google-com'
gd_client.ProgrammaticLogin()
verbose=args.verbose

rootDir = args.directory # set the directory you want to start from
albumNaming = args.naming

albums = Albums(rootDir, albumNaming)
albums.scanWebAlbums()
albums.uploadMissingAlbumsAndFiles(args.compareattributes, args.mode, args.test)

