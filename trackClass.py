#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2021-present, sun-shine cloud, Inc.
# All rights reserved
# 按轨道进行处理相应的数据

import datetime
import os.path
import struct
import sys
import time
import requests

#mp4文件的set内容
class mp4Set():
    trakType = None
    #该内容从mvhd中获取
    volume = None
    #video duration，从mdhd中获取
    duration = None
    # #时间刻度，从mdhd中获取
    timescale = None
    #样例的数量；
    sample_counts = None
    # #时间刻度单位，从stts中获取
    sample_deltas = None                               
    # #Sequence Paramater Set List
    sps = None
    # #Picture Paramater Set List        
    pps = None
    # #video timescale
    # #关键帧序列                
    keys = []         
    # #sample-size 每个视频sample的大小；
    sample_size = []
    # #每个sample所在的chunk        
    chunks_samples = []
    # #每个chunk在文件中的偏移量       
    chunks_offset = []
    sample_offset = []     

class trackClass():
    
    #furl是需要分析的网络文件地址，把远程的文件头读到本地，进行本地文件的处理；
    def __init__(self, trakdata):
        
        self.mset = mp4Set()
        self._trakdata = trakdata
        self.trakType = None
        #该内容从mvhd中获取
        self.volume = None
        #video duration，从mdhd中获取
        self.duration = None
        #时间刻度，从mdhd中获取
        self.timescale = None
        #时间刻度单位，从stts中获取
        self.sample_deltas = None
        self.sample_counts = None
        self._mdia = None
        self._tkhd = None
        self._stbl = None
        self._stss = None
        self._stsc = None
        self._stco = None
        self._stsz = None  
        self._stsd = None
        self._ctts = None                                      
        #Sequence Paramater Set List
        self.sps = None
        #Picture Paramater Set List        
        self.pps = None
        #video timescale
        #关键帧序列                
        self.keys = []         
        #sample-size 每个视频sample的大小；
        self.sample_size = []
        #每个sample所在的chunk        
        self.chunks_samples = []
        #每个chunk在文件中的偏移量       
        self.chunks_offset = []
        #每个sample在chunk的偏移量        
        self.sample_offset = []
        #记录ctts中的data与decode之间的差异
        self.sample_decode_off = []                                                           

    #获取trak中的的Mdia数据内容，并放入self._mdia中；moov->trak->mdia
    def getTrakMdia(self):
        
        seek = 0
        while seek < len(self._trakdata):
            data = self._trakdata[seek:seek+8]
            dlen, dtype = struct.unpack(">I4s", data)
            if dtype == b"mdia":
                self._mdia = self._trakdata[seek+8: seek+dlen]
            # if dtype == b"tkhd":
            #     self._tkhd = trakdata[seek+8: seek+dlen]                
            seek += dlen 


    #从Mdia数据内容中提取mdhd和minf mdia->mdhd minf
    def getTrakMdia_MdhdAndMinf(self):
        
        seek = 0
        while seek < len(self._mdia):
            data = self._mdia[seek:seek+8]
            dlen, dtype = struct.unpack(">I4s", data)
            if dtype == b"mdhd":
                self._mdhd = self._mdia[seek+8: seek+dlen]
            if dtype == b"minf":
                self._minf = self._mdia[seek+8: seek+dlen]               
            seek += dlen

    #从mdhd解析出 duration和timescale
    # 字段	       长度(字节)	描述
    # 尺寸					4	这个atom的字节数
    # 类型					4	mdhd
    # 版本					1	这个atom的版本
    # 标志					3	这里为0
    # 生成时间			 4	Movie atom的起始时间。基准时间是1904-1-1 0:00 AM
    # 修订时间			 4	Movie atom的修订时间。基准时间是1904-1-1 0:00 AM
    # Time scale		4	A time value that indicates the time scale for this media—that is, the number of time units that pass per second in its time coordinate system.
    # Duration		 4	The duration of this media in units of its time scale.
    # 语言					2	媒体的语言码
    # 质量					2	媒体的回放质量？？？怎样生成此质量，什么是参照点
    
    def parseMdhd(self):        
        
        if self._mdhd:
            dt, dd = struct.unpack(">12x4s4s4x", self._mdhd)
            timescale = int.from_bytes(dt, byteorder="big", signed=False)
            duration = int.from_bytes(dd, byteorder="big", signed=False)               
            self.timescale = timescale
            self.duration = duration 

    #获取trak中的的Mdia数据内容，并放入self._mdia中；moov->trak->mdia->minf
    def getTrakMdiaMinfStbl(self):

        seek = 0
        while seek < len(self._minf):
            data = self._minf[seek:seek+8]
            dlen, dtype = struct.unpack(">I4s", data)           
            if dtype == b"vmhd":
                self.trakType = "video"                                  
            if dtype == b"smhd":
                self.trakType = "audio"
            if dtype == b"stbl":
                self._stbl = self._minf[seek+8:seek+dlen]                    
            seek += dlen 

    #获取trak中的的Mdia数据内容，并放入self._mdia中；moov->trak->mdia->vminf->stbl->stss,stsc. stco
    def getTrakMdiaMinfStblAll(self):

        seek = 0
        while seek < len(self._stbl):
            data = self._stbl[seek:seek+8]
            dlen, dtype = struct.unpack(">I4s", data)             
            if dtype == b"stss":
                self._stss = self._stbl[seek: seek+dlen]
            if dtype == b"stsc":
                self._stsc = self._stbl[seek: seek+dlen]
            if dtype == b"stco":
                self._stco = self._stbl[seek: seek+dlen]
            if dtype == b"stsz":
                self._stsz = self._stbl[seek: seek+dlen]
            if dtype == b"stsd":
                self._stsd = self._stbl[seek: seek+dlen]
            if dtype == b"stts":
                self._stts = self._stbl[seek: seek+dlen]  
            if dtype == b"ctts":
                self._ctts = self._stbl[seek: seek+dlen]                                                                                     
            seek += dlen 

    #获取SPS, PPS数据内容，并放入moov->trak->mdia->minf->stbl->avc1->avcC->sps pps
    #MP4的视频H264封装有2种格式：h264和avc1,在此先只实现avc1的内容解析，通过ffmpeg进行封装的基本都是avc1的格式
    def getMediaSpsPps(self):

        if self.trakType != "video":
            return
            
        seek = 0
        avccdata = None
        while seek < len(self._stsd):
            data = self._stsd[seek:seek+8]
            dlen, dtype = struct.unpack(">I4s", data)
            if dtype == b"stsd":
                avc1data = self._stsd[16: dlen]
                data = avc1data[0:8]
                dlen1, dtype1 = struct.unpack(">I4s", data)
                if dtype1 == b"avc1":
                    data2 = avc1data[86: 86+8]
                    dlen2, dtype2 = struct.unpack(">I4s", data2)
                    if dtype2 == b"avcC":
                        avccdata = avc1data[86:86+dlen2]
                        break
        if avccdata:
            #sps的获取需要先从14个字节处取得其数量，第14个字节，前3位为保留位，后5位为数量；
            sps_bt = avccdata[13:14]
            sps_int = int.from_bytes(sps_bt, byteorder="little", signed=False)
            sps_num = sps_int & 31
            soffset = 0    
            for i in range(0, sps_num):
                bsize = avccdata[soffset+14:soffset+14+2]
                bsize_int = int.from_bytes(bsize, byteorder='big', signed=False)
                sps = avccdata[soffset+14+2:soffset+14+2+bsize_int]
                self.sps=sps
                #这个值有可能算的不对，因为多循环的内容没有验证过；
                soffset = bsize_int+2
            pps_bt = avccdata[14+soffset:14+soffset+1]
            pps_num = int.from_bytes(pps_bt, byteorder="little", signed=False)
            soffset+=1
            for i in range(0, pps_num):
                bsize = avccdata[soffset+14:soffset+14+2]
                bsize_int = int.from_bytes(bsize, byteorder='big', signed=False)
                pps = avccdata[soffset+14+2:soffset+14+2+bsize_int]
                self.pps=pps
                #这个值有可能算的不对，因为多循环的内容没有验证过；
                soffset += bsize_int+2                                    
        return                        

    #获取视频中的关键帧的列表；从stss中获取
    def getVideoKeyFrameList(self):

        if self.trakType == "video":
            data = self._stss[:16]
            dlen, dary = struct.unpack(">I8xI", data)
            for i in range(0, dary, 1):
                h_int = int.from_bytes(self._stss[16+i*4:16+i*4+4], byteorder='big', signed=False)
                self.keys.append(h_int)

    #获取视频中的帧的大小；从stsz中获取
    def getSampleSize(self):

        #因为只有一个视频轨，所以只处理一个视频内容即可
        if self._stsz:
            data = self._stsz[:20]
            dary = struct.unpack(">16xI", data)
            for i in range(0, dary[0], 1):
                h_int1 = int.from_bytes(self._stsz[20+i*4:20+i*4+4], byteorder='big', signed=False)                              
                self.sample_size.append(h_int1)                

    #从stts中获取sample_deltas
    def getSampleDeltasAndSampleCount(self):

        if self._stts:
            data = self._stts[:16]
            dary = struct.unpack(">12xI", data)
            for i in range(0, dary[0], 1):
                h_int = int.from_bytes(self._stts[16+i*4:16+i*4+4], byteorder='big', signed=False)
                self.sample_counts = h_int                
                h_int1 = int.from_bytes(self._stts[20+i*4:20+i*4+4], byteorder='big', signed=False)                              
                self.sample_deltas = h_int1

    #获取视频中的帧的每个chunk的偏移量；从stsc中获取
    def getChunkOffset(self):

        if self._stco:
            data = self._stco[:16]
            dlen, dary = struct.unpack(">I8xI", data)
            for i in range(0, dlen, 4):
                h_int1 = int.from_bytes(self._stco[16+i:16+i+4], byteorder='big', signed=False)                              
                self.chunks_offset.append(h_int1)

    #获取视频中的帧的chunk列表；从stsc中获取
    def getSampleChunk(self):

        if self._stsc:
            data = self._stsc[:16]
            dlen, dary = struct.unpack(">I8xI", data)
            o_chunk = 0
            o_num = 0
            for i in range(0, dlen, 12):
                #h_int1为取得的chunk的ID号，从1开始，为了保证后续的简单，把chunk的编号设为从0开始；
                h_int1 = int.from_bytes(self._stsc[16+i:16+i+4], byteorder='big', signed=False)
                h_int2 = int.from_bytes(self._stsc[16+i+4:16+i+8], byteorder='big', signed=False)

                sc = h_int1 - o_chunk - 1
                if sc > 1:
                    for h in range(0, sc, 1):
                        isFirst = True   
                        c_offset = self.chunks_offset[o_chunk]                                                                     
                        o_offset = 0                   
                        for k in range(0, o_num):
                            if isFirst:
                                self.chunks_samples.append(o_chunk)
                                self.sample_offset.append(c_offset)
                                isFirst = False
                                continue                              
                            s_num = len(self.sample_offset)
                            self.chunks_samples.append(o_chunk)
                            o_offset = o_offset + self.sample_size[s_num-1]
                            self.sample_offset.append(c_offset + o_offset)
                            # print(self.sample_size[s_num-1])
                            # print(c_offset + o_offset)
                        o_chunk += 1                                                       

                isFirst = True
                s_offset = self.chunks_offset[h_int1-1]
                o_offset = 0              
                for k in range(0, h_int2):
                    self.chunks_samples.append(h_int1)                    
                    if isFirst:
                        self.sample_offset.append(s_offset)
                        # print(s_offset)                         
                        isFirst = False
                        continue
                    #如果sample_offset中有数据，则取最后的值+sample_size就是本sample的偏移量
                    s_num = len(self.sample_offset)
                    o_offset = o_offset + self.sample_size[s_num-1]
                    # print(self.sample_size[s_num-1])
                    self.sample_offset.append(s_offset+o_offset)
                    # print(s_offset+o_offset)                                                          
                o_chunk = h_int1
                o_num = h_int2
                # print("o_chunk:"+str(o_chunk))
                # print("o_num:"+str(o_num))              
        return  
    #获取各帧的偏移量数据 DTS和PTS的偏移量，有的文章说ctts可能没有，但这个是在有的情况下进行的分析，没有的情况下可能会出错；
    def getPTSDTSOffert(self):

        if self._ctts:
            data = self._ctts[:16]
            dlen, dary = struct.unpack(">I8xI", data)
            for i in range(0, dlen, 8):
                #h_int1为取得的chunk的ID号，从1开始，为了保证后续的简单，把chunk的编号设为从0开始；
                h_int1 = int.from_bytes(self._ctts[16+i:16+i+4], byteorder='big', signed=False)
                h_int2 = int.from_bytes(self._ctts[16+i+4:16+i+8], byteorder='big', signed=False)
                for m in range(0, h_int1):
                    self.sample_decode_off.append(h_int2)
        return 


    def analyze(self):

        self.getTrakMdia()
        self.getTrakMdia_MdhdAndMinf()
        self.parseMdhd()
        self.getTrakMdiaMinfStbl()
        self.getTrakMdiaMinfStblAll()
        self.getVideoKeyFrameList()
        self.getSampleDeltasAndSampleCount()        
        self.getSampleSize()
        self.getChunkOffset()        
        self.getSampleChunk()
        self.getPTSDTSOffert()        
        self.getMediaSpsPps()

        if self.trakType:
            self.mset.trakType = self.trakType
        if self.volume:
            self.mset.volume = self.volume
        if self.duration:
            self.mset.duration = self.duration
        if self.timescale:
            self.mset.timescale = self.timescale
        if self.sample_deltas:
            self.mset.sample_deltas = self.sample_deltas
        if self.sample_counts:
            self.mset.sample_counts = self.sample_counts                           
        if self.sps:
            self.mset.sps = self.sps
        if self.pps:
            self.mset.pps = self.pps           
        if self.keys:
            self.mset.keys = self.keys   
        if self.sample_size:
            self.mset.sample_size = self.sample_size
        if self.chunks_samples:
            self.mset.chunks_samples = self.chunks_samples
        if self.chunks_offset:
            self.mset.chunks_offset = self.chunks_offset
        if self.sample_offset:
            self.mset.sample_offset = self.sample_offset

        return self.mset

    #根据帧序号获取file的偏移量
    def getFileOffsetByFrame(self, nframe):
        #根据nframe号来判定该帧保存在那个chunk中；
        nchunk = self.chunks_samples[nframe -1]
        #根据nchunk来获取该chunk的初始值；
        chunk_offset =  self.chunks_offset[nchunk-1]
        #根据sample的相对值算出sample的偏移量
        s_post = 1
        for k in range (0, nframe, 1):
            if self.chunks_samples[nframe -k - 1] != nchunk:
                s_post = nframe -k + 1
                break

        s_offset = 0
        for m in range(s_post-1, nframe-1, 1):           
            s_offset += self.sample_size[m]
        
        offset = chunk_offset+s_offset
        offset1 = self.sample_offset[nframe-1]
        return

if __name__ == '__main__':

    metad = mp4Set("http://10.10.10.101/lldq.mp4")
    start = datetime.datetime.now()
    metad.loadMetaData()           
    end = datetime.datetime.now()     
    print(str(end-start)+" 秒")
    start = datetime.datetime.now()
    metad.getFileOffsetByFrame(2)
    end = datetime.datetime.now()     
    print(str(end-start)+" 秒")  