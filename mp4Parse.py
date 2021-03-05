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
import urllib.request 

class Mp4Parse():
    
    #furl是需要分析的网络文件地址，把远程的文件头读到本地，进行本地文件的处理；
    def __init__(self, furl):
        
        #设置m3u8的每个时间片的时长为5秒(5000ms)
        self.timeSlice = 10000
        self.furl = furl
        self._boxData = {}
        self._trakdat = []
        self._trak = []
        self._vtrak = []
        self._atrak = []
        #abs_offset 是文件的绝对地址；
        self.abs_offset = 0
        self.vframelist = []
        self.aframelist = []        
                                           
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
            #这部分内容可能会在多个视音频轨时出现问题，后期可以进行改进；
            if mp4set.trakType == "video":
                self._vtrak = mp4set
            if mp4set.trakType == "audio":
                self._atrak = mp4set
        print("aaaaa")

    #根据video track来生成m3u8的内容；
    def mkM3u8(self):

        duration = None
        timescale = None
        sample_deltas = None
        sample_counts = None
        keys = None
        duration = self._vtrak.duration
        timescale = self._vtrak.timescale
        sample_deltas = self._vtrak.sample_deltas
        sample_counts = self._vtrak.sample_counts
        keys = self._vtrak.keys
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

    #根据video请求来的内容来生成TS的文件
    def getFileOffset(self, sframe, eframe):
        vs_off = 0
        ve_off = 0       
        #根据偏移量取得文件中的部分内容；
        vs_off = self._vtrak.sample_offset[sframe-1]
        tnum = len(self._vtrak.sample_offset)
        if eframe >= tnum:
            ve_off = 999999999999999
        else:
            ve_off = self._vtrak.sample_offset[eframe]

        #上面是根据视频文件做的判断，还需要加进音频文件的偏离计算；
        a_sframe, a_eframe = self.getAudioFrameOffset(sframe, eframe)
        as_off = self._atrak.sample_offset[a_sframe-1]
        tnum = len(self._atrak.sample_offset)
        if a_eframe >= tnum:
            ae_off = 999999999999999
        else:
            ae_off = self._atrak.sample_offset[a_eframe]        

        b_begin =  vs_off if as_off > vs_off else as_off
        b_end = ve_off if ae_off < ve_off else ae_off

        self.abs_offset = b_begin
        return b_begin, b_end

    def down_Mp4Slice(self, sframe, eframe):

        s_off, e_off = self.getFileOffset(sframe, eframe)      
        req =  urllib.request.Request('http://10.10.10.101/lldq.mp4') 
        req.add_header('Range', 'bytes='+str(s_off)+'-'+str(e_off)) # set the range, from 0byte to 19byte, 20bytes len 
        res = urllib.request.urlopen(req)         
        data = res.read()
        with open("tmp_data.mp4", "wb+") as f:
            f.write(data)
        return data

    #根据视频的起始帧和终止帧，获取音频的起始和终止帧
    def getAudioFrameOffset(self, sframe, eframe):
        v_timescale = self._vtrak.timescale
        v_deltas = self._vtrak.sample_deltas
        #每帧图片rtik放的时长，为了保证精度，扩大多倍
        v_ftime = (1000000000*v_deltas)/v_timescale
        a_timescale = self._atrak.timescale
        a_deltas = self._atrak.sample_deltas
        #每帧图片rtik放的时长，为了保证精度，扩大多倍
        a_ftime = (1000000000*a_deltas)/a_timescale

        s_time = (sframe - 1)*v_ftime
        t_time = (eframe - sframe + 1) * v_ftime
        #起始时间判定初始的帧 ；
        a_sframe = int(s_time/a_ftime)+1
        a_eframe = a_sframe + int(t_time/a_ftime)
        return a_sframe, a_eframe

    #根据起始的帧和终止帧提取数据中的NALU的内容；
    def getVideoNALUData(self, sframe, eframe):
        
        vdata = self.down_Mp4Slice(sframe, eframe)
        s = eframe - sframe
        s_offset = self.abs_offset
        f = open("lldq_"+str(sframe)+"_"+str(eframe)+".h264", "wb+")
        i_head = struct.pack('3x1b',1)
        f.write(i_head)
        f.write(self._vtrak.sps)
        f.write(i_head)        
        f.write(self._vtrak.pps)        
        for k in range(0, s):
            vdata1 = None
            s_pos =  self._vtrak.sample_offset[sframe+k-1]
            p_size =  self._vtrak.sample_size[sframe+k-1]            
            c_offset = s_pos - s_offset
            #获取前端的4个字节，变换成长度，一个nalu中可能存在多个帧的情况，该种情况，可以通过检查sample_size与s_len的长度来进行判读，
            #如果s_len的长度小于sample_size说明后面还有数据面要处理；
            s_alen = 0
            while True:
                s_len = vdata[c_offset+s_alen:c_offset+4+s_alen]
                h_int = int.from_bytes(s_len, byteorder='big', signed=False)
                vdata1 = vdata[c_offset+s_alen+4:c_offset+4+s_alen+h_int]
                self.vframelist.append(vdata1)
                f.write(i_head)                
                f.write(vdata1)
                # with open("lldq_"+str(10000+k)+".h264", "wb+") as f1:           
                #     f1.write(i_head)
                #     f1.write(vdata1)                  
                s_alen = s_alen + 4 + h_int
                if s_alen >= p_size:
                    break                     

        #音频的内容只能通过时间戳进行定位，首先定位首帧的时间点，然后定位所播放的时长，根据时间点和时长定位音频的内容；
        a_sframe, a_eframe = self.getAudioFrameOffset(sframe, eframe)
        s = a_eframe - a_sframe      
        for k in range(0, s):
            vdata1 = None
            s_pos =  self._atrak.sample_offset[a_sframe+k-1]
            p_size =  self._atrak.sample_size[a_sframe+k-1]            
            c_offset = s_pos - s_offset

            vdata1 = vdata[c_offset+4:c_offset+4+p_size]
            self.aframelist.append(vdata1)
            f.write(i_head)                
            f.write(vdata1)

if __name__ == '__main__':

    metad = Mp4Parse("http://10.10.10.101/lldq.mp4")
    start = datetime.datetime.now()
    metad.getTrack()
    # metad.mkM3u8()
    metad.getVideoNALUData(1, 50)           
    end = datetime.datetime.now()     
    print(str(end-start)+" 秒")
    # start = datetime.datetime.now()
    # metad.getFileOffsetByFrame(2)
    # end = datetime.datetime.now()     
    # print(str(end-start)+" 秒")  