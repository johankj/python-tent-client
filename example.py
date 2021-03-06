#!/usr/bin/env python

from __future__ import division
import pprint, time
import tentapp
from colors import *

def debugJson(s=''): print magenta(pprint.pformat(s))

print yellow('-----------------------------------------------------------------------\\')


# Turn on or off the verbose debug output from tentapp
tentapp.debug = False


# "entity" is the Tent version of a username.  It's a full URL.
# For tent.is it should be "https://yourname.tent.is"
# Instantiating this class will perform discovery on the entity URL
entityUrl = 'https://pythonclienttest.tent.is'
app = tentapp.TentApp(entityUrl)


# Authenticate
# You can use your own database here instead of KeyStore if you want.
# KeyStore just saves the keys to a local JSON file.
keyStore = tentapp.KeyStore('keystore.js')
keys = keyStore.getKey(entityUrl)
if keys:
    # Reuse auth keys from a previous run
    app.authenticate(keys)
else:
    # Get auth keys for the first time
    # and save them into the keyStore
    keys = app.authenticate()
    keyStore.addKey(entityUrl, keys)


# Read various public things that don't require auth
# Note that when auth is present, these may return additional results
print yellow('PROFILE:')
profile = app.getProfile()
debugJson(profile)

print yellow('FOLLOWINGS[0]:')
followings = app.getFollowings()
debugJson(followings[0])

print yellow('FOLLOWERS[0]:')
followers = app.getFollowers()
debugJson(followers[0])

print yellow('POSTS[0]:')
posts = app.getPosts()
debugJson(posts[0])


# Post a new status message
if app.isAuthenticated():
    text = "This is a test message from python-tent-client's example.py.  The time is %s"%int(time.time())
    post = {
        'type': 'https://tent.io/types/post/status/v0.1.0',
        'published_at': int(time.time()),
        'permissions': {
            'public': True,
        },
        'licenses': ['http://creativecommons.org/licenses/by/3.0/'],
        'content': {
            'text': text,
        }
    }
    app.putPost(post)
    print yellow('A message has been posted to pythonclienttest.tent.is:')
    print cyan('    '+text)


print yellow('-----------------------------------------------------------------------/')

