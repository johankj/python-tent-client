#!/usr/bin/env python

from __future__ import division
import time
import random
import os
import pprint
import string
import hashlib
import json
import requests
import webbrowser
import macauthlib
from urllib import urlencode
from urlparse import urlparse
from colors import *


#-------------------------------------------------------------------------------------
#--- UTILS

# Set this to True to get a ton of debugging info printed to the screen
debug = False

def debugAuth(s=''):
    if debug: print blue('%s'%s)
def debugMain(s=''):
    if debug: print yellow('%s'%s)
def debugError(s=''):
    if debug: print red('ERROR: %s'%s)
def debugDetail(s=''):
    if debug: print cyan('    %s'%s)
def debugJson(s=''):
    if debug: print magenta(pprint.pformat(s))
def debugRequest(s=''):
    if debug: print green(' >> %s'%s)
def debugRaw(s=''):
    if debug: print white('>       '+s.replace('\n','\n>       '))

def randomString():
    return ''.join([random.choice(string.letters+string.digits) for x in xrange(20)])

#-------------------------------------------------------------------------------------
#--- CONSTANTS

DEFAULT_HEADERS = {
    'Accept': 'application/vnd.tent.v0+json',
}

#-------------------------------------------------------------------------------------
#--- APP

class TentApp(object):
    def __init__(self,serverDiscoveryUrl=None):
        """The first time you call this, you must set serverDiscoveryUrl.
        After that you can omit it and it will be read from the auth config file.
        If serverDiscoveryUrl is None and there is no auth config file, an error will be raised.
        Upon instantiation a TentApp object will perform server discovery on the serverDiscoveryUrl,
         so you should expect a short delay during instantiation.
        """
        debugMain('init: serverDiscoveryUrl = %s'%serverDiscoveryUrl)

        # path to the config file for saving/loading auth details.
        # TODO: let the user pass this in to the constructor instead of hardcoding it.
        self.configFilePath = 'auth.cfg'

        # details of this app
        #  basic
        self.name = 'python-tent-client'
        self.description = 'description of my test app'

        #  urls
        self.url = 'http://zzzzexample.com'
        self.icon = 'http://zzzzexample.com/icon.png'
        self.oauthCallbackUrl = 'http://zzzzexample.com/oauthcallback'
        self.postNotificationUrl = 'http://zzzzexample.com/notification'

        #  permissions to request
        self.scopes = {
            'read_posts': 'x',
            'write_posts': 'x',
            'import_posts': 'x',
            'read_profile': 'x',
            'write_profile': 'x',
            'read_followers': 'x',
            'write_followers': 'x',
            'read_followings': 'x',
            'write_followings': 'x',
            'read_groups': 'x',
            'write_groups': 'x',
            'read_permissions': 'x',
            'write_permissions': 'x',
            'read_apps': 'x',
            'write_apps': 'x',
            'follow_ui': 'x',
            'read_secrets': 'x',
            'write_secrets': 'x',
        }
        self.profile_info_types = ['all']
        self.post_types = ['all']

        # auth-related things
        #  chosen by us 
        self.state = None

        #  obtained from the server
        self.appID = None # the server assigns this to us during registration

        #  keys
        #   At first these are set to temp values during the registration & oauth approval process.
        #   When that completes, they are replaced with our permanent keys.
        self.mac_key_id = None
        self.mac_key = None
        self.mac_algorithm = None

        # try to load auth details from previously saved config file
        # this will set appID, serverDiscoveryUrl, mac_key_id, and mac_key
        # if no config file exists, this does nothing
        self.serverDiscoveryUrl = None
        self._readConfigFile()

        if serverDiscoveryUrl and serverDiscoveryUrl != self.serverDiscoveryUrl:
            # user has set a specific serverDiscoveryUrl and
            # either this is the first time through (no config file) or the serverDiscoveryUrl
            # is different than the one in the config file, so we need to reset the auth info
            self.serverDiscoveryUrl = serverDiscoveryUrl
            self.appID = None
            self.mac_key_id = None
            self.mac_key = None
            self.mac_algorithm = None

        if serverDiscoveryUrl is None:
            raise "serverDiscoveryUrl was not set in the constructor or the config file"

        # set up default headers for the session
        headers = DEFAULT_HEADERS
        headers.update({
            'Host':urlparse(self.serverDiscoveryUrl).netloc
        })

        # prepare a session for doing requests
        if self.isAuthenticated():
            # if we already have keys from the config file, set up auth now
            debugDetail('building auth session')
            self.session = requests.session(hooks={"pre_request": self._authHook}, headers=headers)
        else:
            # if we don't have auth keys, make a non-auth session.
            # if oauthRegister is run later, this session will be replaced with a session that does authentication
            self.session = requests.session(headers=headers)

        # this list of api roots will be filled in by _discoverAPIurls()
        self.apiRootUrls = []
        self._discoverAPIUrls(self.serverDiscoveryUrl)

    #------------------------------------
    #--- misc helpers

    def isAuthenticated(self):
        return bool(  self.mac_key_id and self.mac_key and self.appID  )

    def _authHook(self,req):
        # hook up sign_request() to be called on every request
        # using the current value of self.mac_key_id and self.mac_key
        debugAuth('auth hook. mac key id: %s'%repr(self.mac_key_id))
        debugAuth('auth hook. mac key: %s'%repr(self.mac_key))
        macauthlib.sign_request(req, id=self.mac_key_id, key=self.mac_key, hashmod=hashlib.sha256)
        return req

    def _writeConfigFile(self):
        debugDetail('writing config file')
        f = open(self.configFilePath,'w')
        f.write(json.dumps({
            'entity': self.serverDiscoveryUrl,
            'appID': self.appID,
            'mac_key_id': self.mac_key_id,
            'mac_key': self.mac_key,
        })+'\n')
        f.close()

    def _readConfigFile(self):
        if not os.path.exists(self.configFilePath):
            debugDetail('no config file exists')
            return
        debugDetail('reading config file')
        jsonObject = json.loads(open(self.configFilePath,'r').read())
        self.appID = jsonObject['appID'].encode('utf-8')
        self.serverDiscoveryUrl = jsonObject['entity'].encode('utf-8')
        self.mac_key_id = jsonObject['mac_key_id'].encode('utf-8')
        self.mac_key = jsonObject['mac_key'].encode('utf-8')
        debugDetail(' config file read for %s'%self.serverDiscoveryUrl)
        debugDetail(' appID = %s'%self.appID)
        debugDetail(' mac_key_id = %s'%self.mac_key_id)
        debugDetail(' mac_key = %s'%self.mac_key)

    #------------------------------------
    #--- server discovery

    def _discoverAPIUrls(self,serverDiscoveryUrl):
        """set self.apiRootUrls, return None
        """
        # get self.serverDiscoveryUrl doing just a HEAD request
        # look in HTTP header for Link: foo; rel="$REL_PROFILE"
        # TODO: if not, get whole page and look for <link href="foo" rel="$REL_PROFILE" />
        debugRequest('head request for discovery: %s'%serverDiscoveryUrl)
        r = requests.head(url=serverDiscoveryUrl)

        # TODO: the requests api here only returns one link even when there are more than one in the
        # header.  I think it returns the last one, but we should be using the first one.
        try:
            self.apiRootUrls = [ r.links['https://tent.io/rels/profile']['url'] ]
        except KeyError:
            # no Link header.  have to look in the body for a <link> tag.
            try:
                r = requests.get(url=serverDiscoveryUrl)
                links = r.text.split('<link')[1:]
                links = [link.split('>')[0] for link in links]
                links = [link for link in links if 'rel="https://tent.io/rels/profile"' in link]
                links = [link.split('href="')[1].split('"')[0] for link in links]
                self.apiRootUrls = links
            except IndexError:
                1/0 # Failure to find a link.  TODO: better error handling

        # remove trailing "/profile" from urls
        for ii in range(len(self.apiRootUrls)):
            self.apiRootUrls[ii] = self.apiRootUrls[ii].replace('/profile','')
            # convert relative urls to absolute
            # this assumes they are relative to the serverDiscoveryUrl
            # this is fragile right now because it assumes the serverDiscoveryUrl doesn't
            # end with a slash
            if not self.apiRootUrls[ii].startswith('http'):
                self.apiRootUrls[ii] = serverDiscoveryUrl + self.apiRootUrls[ii]

        debugDetail('server api urls = %s'%self.apiRootUrls)

    #------------------------------------
    #--- OAuth

    def _register(self):
        # get self.appID and self.mac_* from server
        # return none
        debugMain('registering...')

        # describe ourself to the server
        appInfoJson = {
            'name': self.name,
            'description': self.description,
            'url': self.url,
            'icon': 'http://example.com/icon.png',
            'redirect_uris': [self.oauthCallbackUrl],
            'scopes': self.scopes
        }
        debugJson(appInfoJson)

        # set up default headers for the session
        headers = DEFAULT_HEADERS
        headers.update({
            'Content-Type': 'application/vnd.tent.v0+json',
            'Host':urlparse(self.serverDiscoveryUrl).netloc
        })

        requestUrl = self.apiRootUrls[0] + '/apps'
        debugRequest('posting to %s'%requestUrl)
        r = requests.post(requestUrl, data=json.dumps(appInfoJson), headers=headers)

        # get oauth key in response
        debugDetail('headers from server:')
        debugJson(r.headers)
        debugDetail('json from server:')
        debugJson(r.json)
        if r.json is None:
            debugError('not json.  here is the actual body text:')
            debugRaw(r.text)
            return
        self.appID = r.json['id'].encode('utf-8')
        self.mac_key_id = r.json['mac_key_id'].encode('utf-8')
        self.mac_key = r.json['mac_key'].encode('utf-8')
        self.mac_algorithm = r.json['mac_algorithm'].encode('utf-8')
        debugDetail('registered successfully.  details:')
        debugDetail('  app id: %s'%repr(self.appID))
        debugDetail('  mac key: %s'%repr(self.mac_key))
        debugDetail('  mac key id: %s'%repr(self.mac_key_id))
        debugDetail('  mac algorithm: %s'%repr(self.mac_algorithm))

        # set up a new session that uses MAC authentication
        # this will be used for all future requests
        debugDetail('building auth session')

        # remove the 'Content-Type' header from headers, as it's not needed for all request types
        del headers['Content-Type']

        self.session = requests.session(hooks={"pre_request": self._authHook}, headers=headers)

    def oauthRegister(self):
        """Register this app with the server.
        This will launch a web browser so the user can approve the app.
        If auth keys are already present in this object (beacuse they were laoded
        from a config file) this will return immediately because nothing needs
        to be done.
        """
        # if we already have keys, we don't need to do anything.
        if self.isAuthenticated():
            debugMain('oauth: we already have keys!  doing nothing.')
            return

        # first, register with the server to set
        #  self.appID and self.mac_*
        # this also makes a new self.session which uses MAC authentication
        self._register()

        debugMain('oauth')

        # send user to the tent.is url to grant access
        # we will get the "code" in response
        self.state = randomString()
        params = {
            'client_id': self.appID,
            'redirect_uri': self.oauthCallbackUrl,
            'state': self.state,
            'scope': ','.join(self.scopes.keys()),
            'tent_profile_info_types': 'all',
            'tent_post_types': 'all',
            'tent_notification_url': self.postNotificationUrl,
        }
        requestUrl = self.apiRootUrls[0] + '/oauth/authorize'
        urlWithParams = requestUrl + '?' + urlencode(params)

        print '---------------------------------------------------------\\'
        print
        print 'Opening web browser so you can grant access on your tent server.'
        print
        print 'After you grant access, your browser will be redirected to'
        print 'a nonexistant page.  Look in the url and find the "code"'
        print 'parameter.  Paste it here:'
        print
        print 'Example:'
        print 'http://zzzzexample.com/oauthcallback?code=15673b7718651a4dd53dc7defc88759e&state=ahyKV...'
        print '                                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^'
        print
        webbrowser.open(urlWithParams)
        code = raw_input('> ')
        print
        print '---------------------------------------------------------/'

        # trade the code for a permanent key
        # first make the auth headers using the credentials from the registration step
        resource = '/apps/%s/authorizations'%self.appID
        jsonPayload = {'code':code, 'token_type':'mac'}

        # then construct and send the request
        print
        headers.update({
            'Content-Type': 'application/vnd.tent.v0+json',
        })
        requestUrl = self.apiRootUrls[0] + resource
        debugRequest('posting to: %s'%requestUrl)
        r = self.session.post(requestUrl, data=json.dumps(jsonPayload), headers=headers)

        # display our request
        debugDetail('request headers:')
        debugJson(r.request.headers)
        debugDetail('request data:')
        debugDetail(r.request.data)

        # then get the response
        print
        debugDetail('response headers:')
        debugJson(r.headers)
        debugDetail('response text:')
        debugRaw(r.text)
        if not r.json:
            print
            debugError('auth failed.')
            return
        debugJson(r.json)

        # now we have permanent keys
        self.mac_key_id = r.json['access_token'].encode('utf-8')
        self.mac_key = r.json['mac_key'].encode('utf-8')
        debugDetail('final mac key id: %s'%self.mac_key_id)
        debugDetail('final mac key: %s'%self.mac_key)

        # save the keys to disk
        self._writeConfigFile()
        
    #------------------------------------
    #--- API methods

    def _genericGet(self,resource,**kwargs):
        """Do a get request using the provided kwargs as request parameters.
        """
        requestUrl = self.apiRootUrls[0] + resource
        debugRequest(requestUrl)
        r = self.session.get(requestUrl,params=kwargs)
        if r.json is None:
            debugError('not json.  here is the actual body text:')
            debugRaw(r.text)
            return
        return r.json

    def getProfile(self):
        """Get your own profile.
        """
        # GET /profile
        debugMain('getProfile')
        return self._genericGet('/profile')

    def putProfile(profileType,value):
        """ Set a value for one of the profile types on your profile.
        TODO: not implemented yet.
        """
        # PUT /profile/$profileType
        pass
    
    def follow(self,entityUrl):
        """Begin following the given entity.
        Note that unlike the other follow-related methods, this one uses an entity URL
        instead of an id.
        TODO: not implemented yet.
        """
        # POST /followings
        debugMain('follow')

        resource = '/followings'
        requestUrl = self.apiRootUrls[0] + resource
        headers = DEFAULT_HEADERS
        headers.update({
            'Content-Type': 'application/vnd.tent.v0+json',
        })
        debugRequest('following via: %s'%requestUrl)
        r = self.session.post(requestUrl, data=json.dumps({'entity':entityUrl}), headers=headers)
        
        debugDetail('request headers:')
        debugJson(r.request.headers)
        print
        debugDetail('request data:')
        debugRaw(r.request.data)
        print
        print yellow('  --  --  --  --  --')
        print
        debugDetail('response headers:')
        debugJson(r.headers)
        print
        debugDetail('response body:')
        debugRaw(r.text)
        print
        
        if r.json is None:
            debugError('failed to follow.')
            print
        return r.json

    def getFollowings(self,id=None,**kwargs):
        """Get the entities I'm following.
        Any additional keyword arguments will be passed to the server as request parameters.
        These ones are supported by tentd:
            limit       Max number to return; default to the max of 50
            before_id
            since_id
        """
        # GET /followings  [/$id]
        debugMain('getEntitiesIFollow')
        if id is None:
            return self._genericGet('/followings',**kwargs)
        else:
            return self._genericGet('/followings/%s'%id,**kwargs)

    def unfollow(self,id):
        """Unfollow an entity.
        To get the id, you should first call followings() to get a list of entities and their ids.
        TODO: not implemented yet.
        """
        # DELETE /followings/$id
        debugMain('unfollow')
        resource = '/followings/%s'%id
        requestUrl = self.apiRootUrls[0] + resource
        debugRequest('unfollowing: %s'%requestUrl)
        r = self.session.delete(requestUrl)
        
        debugDetail('request headers:')
        debugJson(r.request.headers)
        print
        print yellow('  --  --  --  --  --')
        print
        debugDetail('response headers:')
        debugJson(r.headers)
        print
        
        if r.status_code is not 200:
            debugError('failed to unfollow.')
            print
            return False
        return True
        

    def getFollowers(self,id=None,**kwargs):
        """Get the entities who are following you.
        Any additional keyword arguments will be passed to the server as request parameters.
        These ones are supported by tentd:
            limit       Max number to return; default to the max of 50
            before_id
            since_id
        """
        # GET /followers  [/$id]
        debugMain('getFollowers')
        if id is None:
            return self._genericGet('/followers',**kwargs)
        else:
            return self._genericGet('/followers/%s'%id,**kwargs)

    def removeFollower(self,id):
        """Cause someone to stop following you?
        The docs are not clear on what this does.
        To get the id, you should first call followers() to get a list of entities and their ids.
        TODO: not implemented yet.
        """
        # DELETE /followers/$id
        pass

    def putPost(self,post,attachments=[]):
        """Post a new post to the server.
        post should be a python dictionary representing a JSON object
        See http://tent.io/docs/post-types for examples.
        TODO: Attachments are not implemented yet.
        """
        # POST /posts
        debugMain('putPost')

        resource = '/posts'
        requestUrl = self.apiRootUrls[0] + resource
        headers = DEFAULT_HEADERS
        headers.update({
            'Content-Type': 'application/vnd.tent.v0+json',
        })
        debugRequest('posting to: %s'%requestUrl)
        r = self.session.post(requestUrl, data=json.dumps(post), headers=headers)

        debugDetail('request headers:')
        debugJson(r.request.headers)
        print
        debugDetail('request data:')
        debugRaw(r.request.data)
        print
        print yellow('  --  --  --  --  --')
        print
        debugDetail('response headers:')
        debugJson(r.headers)
        print
        debugDetail('response body:')
        debugRaw(r.text)
        print

        if r.json is None:
            debugError('failed to put post.')
            print
        return r.json

    def getPosts(self,id=None,**kwargs):
        """With no auth, fetch your own public posts.
        With auth, fetch all your posts plus incoming posts from followings and people mentioning you.
        tent.is limits this to the last 50 posts or so unless additional parameters are present.
        Any additional keyword arguments will be passed to the server as request parameters.
        These ones are supported by tentd:
            limit           Max number to return; default to the max of 50
            before_id
            since_id
            before_time     Time should be an integer in Unix epoch format
            since_time
            entity          Posts published by the specified entity
            post_types      Filter down to these posts types (comma-separated type URIs)
        """
        # GET /posts  [/$id]
        debugMain('getPosts')
        if id is None:
            return self._genericGet('/posts',**kwargs)
        else:
            return self._genericGet('/posts/%s'%id,**kwargs)

    def getPostAttachment(self,id,filename):
        """Get an attachment from a post.
        TODO: not implemented yet.
        """
        # GET /posts/$id/attachments/$filename
        pass





