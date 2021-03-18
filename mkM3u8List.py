#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2021-present, sun-shine cloud, Inc.
# All rights reserved.
# 根据分析mp4的头内容，来产生m3u8的内容文件，切片文件的构成原理是：
# http://10.10.10.101/mp4_md5?start=sframe&end=eframe

from trakData import trakData
from mp4Tools import mp4Tools
from mp4Parse import Mp4Parse

TIME_SLICE = 5000
BASE_URL = "http://10.10.10.101/ts/"

class mkM3u8List():

    def __init__(self, url, mp4_md5):

        #根据mp4_md5获取redis中的数据
        self.mp4_md5 = mp4_md5

        trakdata = trakData()
        vtrak = None
        atrak = None
        vtrak, atrak = trakdata.getTrakData(mp4_md5)

        #如果视频数据没有取出，则需要进行获取，并何存到redis
        if vtrak == None:
            mh = mp4Tools()
            hdata = mh.down_Head(url, mp4_md5)
            if hdata == None:
                return None

            mpp = Mp4Parse(url, hdata, mp4_md5)
            mpp.saveTrakData()

        vtrak, atrak = trakdata.getTrakData(mp4_md5)
        self._vtrak = vtrak
        self._atrak = atrak
        return

    #根据video track来生成m3u8的内容；
    def mk(self):

        duration = None
        timescale = None
        sample_deltas = None
        sample_counts = None
        keys = None
        duration = self._vtrak.duration
        timescale = self._vtrak.timescale
        v_sample_deltas = self._vtrak.sample_deltas
        v_sample_decode_off = self._vtrak.sample_decode_off
        v_sample_counts = len(v_sample_decode_off)      
        keys = self._vtrak.keys
        if not keys:
            return
        #计算每帧的驻留时间,放大100000倍，主要是为了保证精度ftimescale/100000
        ftimescale = (100000000*v_sample_deltas)/timescale
        i = 1
        akey = []
        akey.append(1)
        atime = []
        keys.append(v_sample_counts)
        lastkey = keys[len(keys)-1]

        for ikey in keys:
            akey.append(ikey)
            sumf = ikey - i
            tmf = sumf * ftimescale
            tmf_1 = tmf / 100000
            if (tmf_1 < TIME_SLICE - 1000) and ikey != lastkey:
                akey.pop()
                continue
            atime.append(int(tmf_1))
            i = ikey
        
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
            mt_array.append(BASE_URL+self.mp4_md5+"?start="+str(start)+"&end="+str(end)+"\n")
        mt_array.append("#EXT-X-ENDLIST\n")
        mt_array.insert(0,"#EXTM3U\n")
        mt_array.insert(0,"#EXT-X-VERSION:3\n")
        mt_array.insert(0,"#EXT-X-TARGETDURATION:"+str(int(maxtime+0.99))+"\n")
        mt_array.insert(0,"#EXT-X-MEDIA-SEQUENCE:0\n")

        ret = ""
        with open("test.m3u8", "w") as f:
            for mt in mt_array:
                f.write(mt)
                ret = ret+mt
        return ret