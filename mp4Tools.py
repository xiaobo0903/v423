#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2021-present, sun-shine cloud, Inc.
# All rights reserved
# video on demond to Stream (dts) 
# MP4头文件的获取，一般取前1024x1024的内容(2M)

import datetime
import os.path
import struct
import sys
import time
import requests
from trakClass import trakClass
import urllib.request

HEAD_SIZE = 1024*1024*5

class mp4Tools():

    def __init__(self):
        return

    #下载mp4头
    def down_Head(self, url, mp4_md5):

        _chunk = None
        fn = "./"+mp4_md5
        r = requests.get(url, stream = True)
        try:        
            # with open(fn, 'wb') as f:
            for chunk in r.iter_content(chunk_size = HEAD_SIZE):
                if chunk and r.status_code == 200:
                        # f.write(chunk)
                    _chunk = chunk
                    break
        except:
            _chunk = None
        return _chunk
    
    #根据批定位置，下载
    def down_Mp4Slice(self, url, mp4_md5, s_off, e_off):
   
        # req =  urllib.request.Request(url.decode()) 
        url1 = ""
        if type(url) is bytes:
            url1 = url.decode()
        else:
            url1 = url
        req =  urllib.request.Request(url1) 
        req.add_header('Range', 'bytes='+str(s_off)+'-'+str(e_off)) # set the range, from 0byte to 19byte, 20bytes len 
        res = urllib.request.urlopen(req)         
        data = None
        try:
            data = res.read()
            # with open(mp4_md5+"_"+str(s_off)+"_"+str(e_off)+".mp4", "wb+") as f:
            #     f.write(data)
            return data
        except:
            return None