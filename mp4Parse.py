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
from trackClass import trackClass
from hashlib import md5

class Mp4Parse():
    
    #furl是需要分析的网络文件地址，把远程的文件头读到本地，进行本地文件的处理；
    def __init__(self, furl):
        
        #设置m3u8的每个时间片的时长为5秒(5000ms)
        self.timeSlice = 10000
        self.furl = furl
        self._boxData = {}
        self._trakdat = []
        self._trak = []
                                           
        self.fn = "./"+md5(furl.encode("utf8")).hexdigest()
        r = requests.get(furl, stream = True)
        # download started
        with open(self.fn, 'wb') as f:
            for chunk in r.iter_content(chunk_size = 1024*1024*8):
                if chunk:
                    f.write(chunk)
                    self._chunk = chunk
                    break

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
    def getTrackDat(self):
        seek = 0
        adata = self._boxData[b"moov"]
        while seek < len(adata):
            data = adata[seek:seek+8]
            dlen, dtype = struct.unpack(">I4s", data)
            if dtype == b"trak":
                self._trakdat.append(adata[seek+8:seek+dlen])
            seek += dlen

    #根据track中的数据，解析出所需要的内容；
    def getTrack(self):

        self.getOneBoxData()
        self.getTrackDat()
        for tdat in self._trakdat: 
            trakclass = trackClass(tdat)
            mp4set = trakclass.analyze()
            self._trak.append(mp4set)
        print("aaaaa")

    #根据video track来生成m3u8的内容；
    def mkM3u8(self):

        duration = None
        timescale = None
        sample_deltas = None
        sample_counts = None
        keys = None
        for trak in self._trak:
            if trak.trakType == "video":
                duration = trak.duration
                timescale = trak.timescale
                sample_deltas = trak.sample_deltas
                sample_counts = trak.sample_counts
                keys = trak.keys
                break
        if not keys:
            return
        #计算每帧的驻留时间,放大100000倍，主要是为了保证精度ftimescale/100000
        ftimescale = (100000000*sample_deltas)/timescale
        i = 1
        akey = []
        akey.append(1)
        atime = []
        keys.append(sample_counts)
        lastkey = keys[len(keys)-1]
        for key in keys:
            akey.append(key)
            sumf = key - i
            tmf = sumf * ftimescale
            tmf_1 = tmf / 100000
            if (tmf_1 < self.timeSlice - 1000) and key != lastkey:
                akey.pop()
                continue
            atime.append(int(tmf_1))
            i = key
        
        #生成m3u8的播放列表，
        # #EXTM3U
        # #EXT-X-VERSION:3
        # #EXT-X-TARGETDURATION:12
        # #EXT-X-MEDIA-SEQUENCE:0
        # #EXTINF:11.11,
        # TEST_SHANDONG007_1200/1.ts?startoffset=0&endoffset=1388192
        # #EXTINF:11.06,
        # TEST_SHANDONG007_1200/2.ts?startoffset=1388192&endoffset=2770932
        # #EXT-X-ENDLIST
        
        maxtime = 0
        nstr = str(datetime.datetime.now())
        mt_array = []
        for i in range(0, len(akey)-1):
            start = akey[i]
            end = akey[i+1]
            if end != lastkey:
                end = end -1
            sduration = float(atime[i]/1000)
            if maxtime < sduration:
                maxtime = sduration
            mt_array.append("#EXTINF:"+str(sduration)+",\n")
            mt_array.append("http://10.10.10.101/lldq.ts?start="+str(start)+"&end="+str(end)+"\n")
        mt_array.append("#EXT-X-ENDLIST\n")
        mt_array.insert(0,"#EXTM3U\n")
        mt_array.insert(0,"#EXT-X-VERSION:3\n")
        mt_array.insert(0,"#EXT-X-TARGETDURATION:"+str(int(maxtime+0.99))+"\n")
        mt_array.insert(0,"#EXT-X-MEDIA-SEQUENCE:0\n")

        with open("test.m3u8", "w") as f:
            for mt in mt_array:
                f.write(mt)

if __name__ == '__main__':

    metad = Mp4Parse("http://10.10.10.101/lldq.mp4")
    start = datetime.datetime.now()
    metad.getTrack()
    metad.mkM3u8()           
    end = datetime.datetime.now()     
    print(str(end-start)+" 秒")
    # start = datetime.datetime.now()
    # metad.getFileOffsetByFrame(2)
    # end = datetime.datetime.now()     
    # print(str(end-start)+" 秒")  