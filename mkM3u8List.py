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
import cfg

TIME_SLICE = 10

class mkM3u8List():

    def __init__(self, url, mp4_md5):

        self.cfg = cfg.cfgClass()
        #根据mp4_md5获取redis中的数据
        self.mp4_md5 = mp4_md5

        trakdata = trakData()
        vtrak = None
        atrak = None
        vtrak, atrak = trakdata.getTrakData(mp4_md5)

        #如果视频数据没有取出，则需要进行获取，并何存到redis
        if vtrak == None:
            mh = mp4Tools()
            hdata = mh.down_Mp4Slice(url, mp4_md5, 0, 2048)
            # hdata = mh.down_Head(url, mp4_md5)
            if hdata == None:
                return None

            mpp = Mp4Parse(url, mp4_md5)
            begin, end = mpp.getMoovOffset(hdata)
            moov_data = mh.down_Mp4Slice(url, mp4_md5, begin, end)
            #把解析出的视频和音频轨的数据放入到redis数据库中
            mpp.saveTrakData(moov_data)
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
        v_sample_time_site = self._vtrak.sample_time_site
        v_sample_counts = len(v_sample_decode_off)      
        keys = self._vtrak.keys
        
        if not keys:
            return
        
        #帧时间的计算公式为：
        # timescale 和帧的偏移时间，key_timescale,如果一个帧的时间刻度是24000，而偏移值为 5000,则计算公式为, 1000*(offset/duration)得到毫秒数


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

        #以下计算的是生成片段的长度，生成每片内容有两个条件，一个是起始点一定是一个帧，就是帧的编号一定是在keys中， 一个是符合TIME_SLICE时间的要求；
        # 就是在TIME_SLICE时间段内查找最小关键帧的内容；
        
        mt_array = []
        maxtime = 0
        time_scale = (TIME_SLICE - 2) * timescale
        start = 0
        end = 0
        p_time = 0
        for i in keys:

            k_time = v_sample_time_site[i]
            if k_time - p_time < time_scale:
                continue

            end = i - 1
            sduration = (k_time - p_time)/timescale
            if sduration > maxtime:
                maxtime = sduration
            p_time = k_time
            mt_array.append("#EXTINF:"+str(round(sduration, 3))+",\n")
            mt_array.append(self.cfg.BASE_URL+self.mp4_md5+".ts?start="+str(start)+"&end="+str(end)+"\n")
            p_time = k_time
            start = i
    #因为最后一个关键帧，还需要有一个段的内容到结尾；
        if start != v_sample_counts - 1:
            k_time = v_sample_time_site[v_sample_counts-1]
            sduration = (k_time - p_time)/timescale
            if sduration > maxtime:
                maxtime = sduration
            mt_array.append("#EXTINF:"+str(round(sduration, 3))+",\n")
            mt_array.append(self.cfg.BASE_URL+self.mp4_md5+".ts?start="+str(start)+"&end="+str(v_sample_counts - 1)+"\n")

        mt_array.append("#EXT-X-ENDLIST\n")
        mt_array.insert(0,"#EXT-X-TARGETDURATION:"+str(int(maxtime+0.99999))+"\n")
        mt_array.insert(0,"#EXT-X-ALLOW-CACHE:YES\n")
        mt_array.insert(0,"#EXT-X-MEDIA-SEQUENCE:0\n")
        mt_array.insert(0,"#EXT-X-VERSION:3\n")
        mt_array.insert(0,"#EXTM3U\n")

        ret = ""
        # with open("test.m3u8", "w") as f:
        #     for mt in mt_array:
        #         f.write(mt)
        #         ret = ret+mt
        for mt in mt_array:
            ret = ret+mt

        return ret