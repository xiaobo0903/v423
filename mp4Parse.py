#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2021-present, sun-shine cloud, Inc.
# All rights reserved.
# 基于mp4封装格式的moov解析，
#     1、首先通过提取stss内容，生成关键帧信息
#     2、根据
import datetime
import os.path
import struct
import sys
import time
import requests
from trakClass import trakClass
from hashlib import md5
import urllib.request
from trakData import trakData

class Mp4Parse():
    
    #furl是需要分析的网络文件地址，把远程的文件头读到本地，进行本地文件的处理；
    def __init__(self, url, head_chunk, mp4_md5):
        
        #设置m3u8的每个时间片的时长为5秒(5000ms)
        self.mp4_md5 = mp4_md5
        self.url = url
        self.timeSlice = 10000
        self._boxData = {}
        self._trakdat = []
        self._trak = []
        self._vtrak = []
        self._atrak = []
        #abs_offset 是文件的绝对地址；
        self.abs_offset = 0
        self.vframelist = []
        self.aframelist = []
        self._chunk = head_chunk       
                                           
    #获取mp4第一层的数据,ftyp和moov的数据
    def getOneBoxData(self):
        seek = 0
        while seek < len(self._chunk):
            data = self._chunk[seek:seek+8]
            dlen, dtype = struct.unpack(">I4s", data)
            print(dtype)
            self._boxData[dtype] = self._chunk[seek+8:dlen]
            seek += dlen            
            if dtype == b"moov":
                break
 
    #获取mp4第二层的数据,解析moov的数据(mvhd,iods,trak)
    def getTrakDat(self):
        seek = 0
        adata = self._boxData[b"moov"]
        while seek < len(adata):
            data = adata[seek:seek+8]
            dlen, dtype = struct.unpack(">I4s", data)
            if dtype == b"trak":
                self._trakdat.append(adata[seek+8:seek+dlen])
            seek += dlen

    #根据trak中的数据，解析出所需要的内容；
    def getTrak(self):

        self.getOneBoxData()
        self.getTrakDat()
        for tdat in self._trakdat: 
            trakclass = trakClass(tdat)
            mp4set = trakclass.analyze()
            #这部分内容可能会在多个视音频轨时出现问题，后期可以进行改进；
            if mp4set.trakType == "video":
                self._vtrak = mp4set
            if mp4set.trakType == "audio":
                self._atrak = mp4set

    #save Trak to Redis
    def saveTrakData(self):
        self.getTrak()
        trakdata = trakData()         
        trakdata.putTrakData(self.url, self.mp4_md5, self._vtrak, self._atrak)

if __name__ == '__main__':

    metad = Mp4Parse("http://10.10.10.101/lldq.mp4")
    start = datetime.datetime.now()
    metad.getTrak()
    metad.mkM3u8()
    #获取180140&end=180168
    metad.getVideoNALUData(180140, 180168)           
    end = datetime.datetime.now()     
    print(str(end-start)+" 秒")
    # start = datetime.datetime.now()
    # metad.getFileOffsetByFrame(2)
    # end = datetime.datetime.now()     
    # print(str(end-start)+" 秒")  