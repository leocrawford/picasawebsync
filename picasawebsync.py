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

# Class to store details of an album

supportedImageFormats = frozenset(["image/bmp", "image/gif",  "image/jpeg",  "image/png"])
activityLevels = ["none", "upload", "replace", "delete", "overwrite"]

class Albums:
    def __init__(self, rootDir, albumNaming):
        self.albums = Albums.scanFileSystem(rootDir, albumNaming)
    # walk the directory tree populating the list of files we have locally
    @staticmethod
    def scanFileSystem(rootDir, albumNaming):
        fileAlbums = {}
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
                fileEntry = FileEntry(relFileName, fullFilename,  False, True)
                album.entries[relFileName] = fileEntry
        print "Found "+str(len(fileAlbums))+" albums on the filesystem"
        return fileAlbums;
    def scanWebAlbums(self):
        # walk the web album finding albums there
        webAlbums = gd_client.GetUserFeed()
        for webAlbum in webAlbums.entry:
            webAlbumTitle = Albums.flatten(webAlbum.title.text)
            if webAlbumTitle in self.albums:
                foundAlbum = self.albums[webAlbumTitle]
                photos = gd_client.GetFeed(webAlbum.GetPhotosUri())
                foundAlbum.webAlbum.append(WebAlbum(webAlbum, int(photos.total_results.text)))
                for photo in photos.entry:
                    if photo.title.text in foundAlbum.entries: 
                        foundAlbum.entries[photo.title.text].isWeb = True
                    else:
                        print "skipping web only photo "+photo.title.text
            else:
                print "skipping web only album "+webAlbum.title.text 
            print 'Checked: %s (containing %s files)' % (webAlbum.title.text, webAlbum.numphotos.text)
    def uploadMissingAlbumsAndFiles(self,  remoteLevel, metadataLevel):
        for album in self.albums.itervalues():
            for file in album.entries.itervalues():
                if file.isLocal: 
                    if file.isWeb:
                        print "Nothing to do with %s as local and remote" % file.path
                    else:
                        album.upload(file, remoteLevel)
                else:
                    if file.isWeb:
                        print "Download to local not yet supported for %s" % file.path
                    else:
                        print "There is no way a file can be neither remote or local. Error! %s" % file.path
                            


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
    def upload(self, file,  remoteLevel):
        if(remoteLevel >= 1):
            while (self.webAlbumIndex<len(self.webAlbum) and self.webAlbum[self.webAlbumIndex].numberFiles >= 999):
                self.webAlbumIndex = self.webAlbumIndex + 1                        
            if self.webAlbumIndex>=len(self.webAlbum):
                subAlbum = WebAlbum(gd_client.InsertAlbum(title=Albums.createAlbumName(self.getAlbumName(), self.webAlbumIndex), access='private', summary='synced from '+self.rootPath), 0)
                self.webAlbum.append(subAlbum)
                print 'Created album %s to sync %s' % (subAlbum.album.title.text, self.rootPath)
            else:
                subAlbum = self.webAlbum[self.webAlbumIndex]
            photo = self.upload2(subAlbum, file,  remoteLevel)    
        else:
            print "Skipped upload of %s as not instructed to upload" % file.path
    def upload2(self,  subAlbum,  file,  remoteLevel):
        try:
            mimeType = mimetypes.guess_type(file.path)[0]
            if mimeType in supportedImageFormats:
                metadata = gdata.photos.PhotoEntry()
                metadata.title=atom.Title(text=file.name)
                metadata.summary = atom.Summary(text='synced from xxx'+file.path, summary_type='text')
                metadata.checksum= gdata.photos.Checksum("XXX")
                photo = gd_client.InsertPhoto(subAlbum.album, metadata, file.path, mimeType)
                print "uploaded "+file.path
                subAlbum.numberFiles = subAlbum.numberFiles + 1
                return photo
            else:
                print "Skipped %s (because can't upload file of type %s)." % (file.path, mimeType)
        except GooglePhotosException:
            print "Skipping upload of %s due to exception" % file.path 
    
# Class to store web album details

class WebAlbum:
    def __init__(self, album,  numberFiles):
        self.album = album
        self.numberFiles = numberFiles


# Class to store details of an individual file

class FileEntry:
    def __init__(self, name, path,  isWeb,  isLocal):
        self.name = name
        self.path=path
        self.isWeb=isWeb
        self.isLocal=isLocal
    
    
# Method to translate directory name to an album name   
    
def convertDirToAlbum(form,  root,  name):
    formElements = re.split("~", form)
    nameElements = re.split("/", re.sub("^/","",name[len(root):]))
    which = min(len(formElements), len(nameElements))
    work = formElements[which-1].format(*nameElements)
    return work

# start of the program

def convertImpactLevel(string):
    i = activityLevels.index(string)
    return i

parser = argparse.ArgumentParser()
parser.add_argument("username", help="Your picassaweb username")
parser.add_argument("password", help="Your picassaweb password")
parser.add_argument("directory",  help="The local directory to copy from")
parser.add_argument("-n","--naming", default="{0}~{1} ({0})",  help="Expression to convert directory names to web album names. Formed as a ~ seperated list of substitution strings, "
"so if a sub directory is in the root scanning directory then the first slement will be used, if there is a directory between them the second, etc. If the directory path is longer than the "
"list then the last element is used (and thus the path is flattened)")
parser.add_argument("-r", "--remotelevel", type=convertImpactLevel, help="upload level %s" % list(activityLevels),  default="upload")
parser.add_argument("-m", "--metadatalevel", type=convertImpactLevel, help="metadata level %s" % list(activityLevels),  default="upload")
args = parser.parse_args()

gd_client = gdata.photos.service.PhotosService()
gd_client.email = args.username # Set your Picasaweb e-mail address...
gd_client.password = args.password 
gd_client.source = 'api-sample-google-com'
gd_client.ProgrammaticLogin()

rootDir = args.directory # set the directory you want to start from
albumNaming = args.naming

albums = Albums(rootDir, albumNaming)
albums.scanWebAlbums()
albums.uploadMissingAlbumsAndFiles(args.remotelevel, args.metadatalevel)


exit(1)


        
  
sys.exit(0)


#    photos = gd_client.GetFeed('/data/feed/api/user/default/albumid/%s?kind=photo' % (album.gphoto_id.text))
#  for photo in photos.entry:
#       print '  Photo:', photo.title.text

#    tags = gd_client.GetFeed('/data/feed/api/user/default/albumid/%s/photoid/%s?kind=tag' % (album.gphoto_id.text, photo.gphoto_id.text))
#    for tag in tags.entry:
#      print '    Tag:', tag.title.text

#    comments = gd_client.GetFeed('/data/feed/api/user/default/albumid/%s/photoid/%s?kind=comment' % (album.gphoto_id.text, photo.gphoto_id.text))
#    for comment in comments.entry:
#      print '    Comment:', comment.content.text
