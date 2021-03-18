#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2021-present, sun-shine cloud, Inc.
# All rights reserved
# video on demond to Stream (dts) 
# 解析mp4的头数据，并保存到redis中
import pickle
import redis
from trakClass import mp4Set

# 
class trakData():

    def __init__(self):
        return

    #把trak1,trak2的数据放到redis中
    def putTrakData(self, url, mp4_md5, vdset, adset):

        rs = redis.Redis(host='localhost', port=6379,  db=1)
        # pickle and set in redis
        rs.setex('v_'+mp4_md5, 60*60*24*30, pickle.dumps(vdset))
        rs.setex('a_'+mp4_md5, 60*60*24*30, pickle.dumps(adset))
        rs.setex('u_'+mp4_md5, 60*60*24*30, url)               

    #从redis中取出trak1
    def getTrakData(self, mp4_md5):
     
        try:
            rs = redis.Redis(host='localhost', port=6379, db=1)
            vdset = pickle.loads(rs.get('v_'+mp4_md5))
            adset = pickle.loads(rs.get('a_'+mp4_md5))                 
            return vdset, adset
        except:
            return None, None

    #从redis中取出url
    def getMp4Url(self, mp4_md5):
     
        try:
            rs = redis.Redis(host='localhost', port=6379, db=1)
            url = rs.get('u_'+mp4_md5)             
            return url
        except:
            return None