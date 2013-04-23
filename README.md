# picasawebsync

This python utility will allow you to sync local directories with picasaweb. I'd appreciate feedback if you find it useful, or find problems. I run it over a 36000+ item collection on a linux box (netgear readynas v2) without problems. 

## Features

Currently it supports:

* Upload only (from local filesystem to picasaweb)
* Flattening (so that deep directroy hierarachies on the local filesystem are collapsed into a single web album)
* Smart web album naming (so that you can choose which elements of the directory path you'd like to retain)
* Large album support (so that directories with more than 1000 items are mapped to multiple sequenced web albums)
* Multi-layered approach to detecting file change, including timestamp, filesize and hash of file
* User-id and password log-on
* Install scripts
* Two way sync 
* Optional deletion 
* Delete empty remote directories (see purge option)
* Confirmation params to enable delete (local and remote) using the --allowDelete option
* Cross platform (python based)
* Works on headless systems
* Add maximum size for videos to save slow failed uploads
* Option to shrink (reduce) photos to the 2048x2048 pixel limit imposed by google (may stop some of the sync capabilities from working)
* Write album date (based on the earliest date form the set of images within it). 
* Meta-data repair (e.g. album metadata, or image hash and date)

Soon to be supported:

* Support for browser based log-on so you don't need to tell the app your details
* A better installation process. 
* Handle mutiple files of same name, which are flattened into the same remote directory

## Installation

1. Install you have python >=2.7 <3 installed (these version numbers are based on some assumptions, so I could be wrong), make sure it has SSL support enabled
2. Install PIL package (text taken from http://gausssum.sourceforge.net/DocBook/ch01s03.html)
    You can get PIL 1.1.7 from here under "Python Imaging Library 1.1.7 Source Kit (all platforms)". This should be untarred into a folder in the usual way, using
    
    tar zxvf Imaging-1.1.7.tar.gz
    
    Next, go into the folder created and (as root) install the package as follows: 
    
    python setup.py install
    
    If you are using Debian Linux, the Python Imaging Library will be downloaded and installed if you issue the following command as root: 
    
    apt-get install python-imaging python-imaging-tk
3. Add the gdata packages 

    cd /tmp
    wget https://gdata-python-client.googlecode.com/files/gdata-2.0.17.zip
    unzip gdata*
    python setup.py install

    or debian/ubuntu way 

    apt-get install python-gdata

4. download the latest version from the releases directory
5. untar it to a temporary directory (tar zxvf <filename> should work for most Linux distros)
6. (optionally) install it using 

    python setup.py install  (you may need sudo for linux platforms)

If you're able to help with a better installation process please shout

## Running it

### The basics 

The minimum command is 

    ./picasawebsync -u <username> -p <password> -d <one or more local directories>
    
Note: If python is installed in an usual place you might need to use:

    python picasawebsync -u <username> -p <password> -d <one or more local directories>

### The settings

#### Directory

The directory setting is a list of path names. They must all be directories. If any files are downloaded from a web album without a corresponding local album - it will be the first of these that is chosen.

#### Naming

In order to convery directory names into "beautiful" web abum names we need to do a mapping. The premise of the mapping is a list of transformations, one for directory paths that are one deep, the next for two deep, 
the next for three deep, etc. etc.

Because that doesn't cope well with very deep directory structures the app will simply use the longest one there if there isn't one long enough. This lets us do clever things like out-of-order directory names.

As a real example my photos are indexed by year / albumName so I choose to use a mapping of {0} for files under directly a year, but {1} ({0}) for all otehrs which gives me the album name first, then the year in brackets. 
All extra paths (e.g. photographer or sub-trip location) are simply forgotton.

As will be apparant from the above example the actual substitutions are simple substitutions of the form {x} where x is the position in the directory path (0 is far left) that we should use. 

For example

    a/b/c/d formatted using -n {0} is a
    a/b/c/d formatted using -n {0}{1}-kkk-{0} is b-kkk-a
    a/b/c/d formatted using -n {0} {0} {1}-kkk-{0} is b-kkk-a
    a/b/c/d formatted using -n {0} {0} {0} {0} {1}-kkk-{0} is a   
    a/b/c/d formatted using -n {0} {0} {0} {0}@{1} {1}-kkk-{0} is a@b
    
You can also supply regex capture and replace expression

    base-kkk-aaaa formatted using --namingextract '([a-z]*)-kkk-([a-z]*)|\2 (\1)' is base (aaaa)

Then you can apply final replacement

    my-photo-dir formatted using -r '-| ' is my photo dir

#### Mode

The -m or --mode option takes  a name (one of upload, download, repairUpload, report, sync) which correspond to the settings below.

For each mode there are a set of events (left) and actions (right). When the event occurs the action on the right is invoked. By changing the mode you can therefore choose whether to do a download, and upload or something more complex.

If you want to simply see what events are triggered run with report. If you want to simulate a run use the -t or --test option

    UploadOnlyActions = {
            Comparisons.REMOTE_OLDER:Actions.REPLACE_REMOTE_WITH_LOCAL, 
            Comparisons.DIFFERENT:Actions.REPORT, 
            Comparisons.SAME:Actions.SILENT, 
            Comparisons.UNKNOWN:Actions.REPORT, 
            Comparisons.LOCAL_ONLY:Actions.UPLOAD_LOCAL, 
            Comparisons.REMOTE_ONLY:Actions.REPORT}
    DownloadOnlyActions = {
            Comparisons.REMOTE_OLDER:Actions.REPORT, 
            Comparisons.DIFFERENT:Actions.DOWNLOAD_REMOTE, 
            Comparisons.SAME:Actions.SILENT, 
            Comparisons.UNKNOWN:Actions.REPORT, 
            Comparisons.LOCAL_ONLY:Actions.REPORT, 
            Comparisons.REMOTE_ONLY:Actions.DOWNLOAD_REMOTE}
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
            Comparisons.SAME:Actions.SILENT,  
            Comparisons.UNKNOWN:Actions.UPDATE_REMOTE_METADATA, 
            Comparisons.LOCAL_ONLY:Actions.UPLOAD_LOCAL, 
            Comparisons.REMOTE_ONLY:Actions.DELETE_REMOTE}
    SyncActions= {
            Comparisons.REMOTE_OLDER:Actions.REPLACE_REMOTE_WITH_LOCAL, 
            Comparisons.DIFFERENT:Actions.REPORT, 
            Comparisons.SAME:Actions.SILENT,  
            Comparisons.UNKNOWN:Actions.REPORT, 
            Comparisons.LOCAL_ONLY:Actions.UPLOAD_LOCAL, 
            Comparisons.REMOTE_ONLY:Actions.DOWNLOAD_REMOTE}
    SyncUploadActions= {
            Comparisons.REMOTE_OLDER:Actions.REPLACE_REMOTE_WITH_LOCAL, 
            Comparisons.DIFFERENT:Actions.REPLACE_REMOTE_WITH_LOCAL, 
            Comparisons.SAME:Actions.SILENT,  
            Comparisons.UNKNOWN:Actions.REPLACE_REMOTE_WITH_LOCAL, 
            Comparisons.LOCAL_ONLY:Actions.UPLOAD_LOCAL, 
            Comparisons.REMOTE_ONLY:Actions.DELETE_REMOTE}

#### Comparisons

Two files with an identical name are considered to be the same file, but in order to evaluate whether the the file has changed (and potentially needs to be re-uploaded) there are three approaches that can be used:

1. Date of last update
2. Filesize
3. Hash (expensive operation as the fille needs to be re-hashed locally on every scan)

Therefore the default is to use a combination of 1 and 2. Other options are set using and and operation, as below:

    -c 1 # Date
    -c 2 # Filesize
    -c 3 # Date and filesize (default)
    -c 4 # Hash
    -c 5 # Hash and date
    -c 6 # hash and filesize
    -c 7 # date filesize and hash

### Examples

    ./picasawebsync.py -u <email> -p <password> -d testdata -m syncUpload # upload any files from local that are missing on remote or different. Report remote files that are not local
    ./picasawebsync.py -u <email> -p <password> -d testdata -m syncUpload --allowDelete remote # upload any files from local that are missing on remote or different. Delete remote files that are not local
    ./picasawebsync.py -u <email> -p <password> -d testdata -m syncUpload --allowDelete remote --override:SAME UPDATE_REMOTE_METADATA --noupdatealbummetadata # As above bus also update metadata for each remote item, this also causes album metadata to be updated (so album dates can be refreshed)
    ./picasawebsync.py -u <email> -p <password> -d testdata -m syncUpload -c1 # upload any files from local that are missing on remote or different (different determined by file date only). Report remote files that are not local.   
    ./picasawebsync.py -u <email> -p <password> -d testdata -m syncUpload -c5 # upload any files from local that are missing on remote or different (different determined by file date, size and hash). Report remote files that are not local.   
    ./picasawebsync.py -u <email> -p <password> -d testdata -m downloadOnly # download any remote files that aren't local or are different, unless known to be older (in which case report)
    ./picasawebsync.py -u <email> -p <password> -d testdata -m downloadOnly --override:REMOTE_OLDER DOWNLOAD_REMOTE # download any remote files that aren't local or are different, even if known to be older    




    



Notes
--------

An upload can be one of:

upload: "none", "upload", "replace", "delete", "overwrite"
metadata: "none", "upload", "replace", "delete", "overwrite"


    LOCAL_ONLY->Upload_local, Delete_local, Skip, Skip_report
    REMOTE_ONLY->Download_remote, Delete_remote, Tag_remote, Skip, Skip_report
    REMOTE_OLDER->Upload_local, Skip, Skip_report
    DIFFERENT->Upload_local,Download_remote,Upload_local_metadata, Skip, Skip_report
    SAME->Upload_local,Download_remote,Upload_local_metadata, Skip, Skip_report
    UNKNOWN (No hash)->Upload_local,Download_remote,Upload_local_metadata, Skip, Skip_report

python setup.py sdist
