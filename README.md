picasawebsync
=============

This python utility will allow you to sync local directories with picasaweb. It is very much in alpha state so please provdie feedback

Currently it supports:

* Upload only (from local filesystem to picasaweb)
* Flattening (so that deep directroy hierarachies on the local filesystem are collapsed into a single web album)
* Smart web album naming (so that you can choose which elements of the directory path you'd like to retain)
* Large album support (so that directories with more than 1000 items are mapped to multiple sequenced web albums)
* Hashing to ensure that changed files are picked up

Soon to be supported:

* Two way sync
* Optional deletion (local and web)

Notes
--------

An upload can be one of:

upload: "none", "upload", "replace", "delete", "overwrite"
metadata: "none", "upload", "replace", "delete", "overwrite"

check-mechnism: Filename, Date, Hash

