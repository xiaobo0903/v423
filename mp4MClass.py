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
from hashlib import md5

class Mp4MetaData():
    
    #furl是需要分析的网络文件地址，把远程的文件头读到本地，进行本地文件的处理；
    def __init__(self, furl):
        
        self.furl = furl
        self._boxData = {}
        self._trak = []
        self._mdia = []
        self._vminf = []
        self._aminf = []
        self._vstbl = []
        self._vstss = [] 
        self._vstsc = []
        self._vstco = []
        self._vstsz = []
        self._vstsd = []        
        self._vavc1 = []        
        self._astbl = []
        self._astsc = []
        self._astco = []
        self._astsz = []
        #关键帧序列                
        self.keys = []
        #Sequence Paramater Set List
        self.sps = []
        #Picture Paramater Set List        
        self.pps = []
        #video timescale
        self.vtimescale = None
        #audio timescale
        self.atimescale = None
        #video duration
        self.vduration = None
        #audio duration        
        self.aduration = None
        #video frame duration
        self.vfduration = None
        #audio frame duration        
        self.afduration = None                 
        #sample-size 每个视频sample的大小；
        self.sample_size = []
        #每个sample所在的chunk        
        self.chunks_samples = []
        #每个chunk在文件中的偏移量       
        self.chunks_offset = []
        #每个音频的sample的大小 
        self.asample_size = []
        #每个音频所在的chunk                
        self.achunks_samples = []
        #每个音频所在chunk的偏移量        
        self.achunks_offset = []                                           
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
    def getMoovData(self):
        seek = 0
        adata = self._boxData[b"moov"]
        while seek < len(adata):
            data = adata[seek:seek+8]
            dlen, dtype = struct.unpack(">I4s", data)
            if dtype == b"mvhd":
                self.getMoovHeadMvhd(adata[:dlen])
            if dtype == b"trak":
                self._trak.append(adata[seek+8:seek+dlen])
            seek += dlen            

    #获取moov中mvhd的数据 mvhd共为216个字节；moov->mvhd
    def getMoovHeadMvhd(self, data):
        seek = 0
        fmt = ">I4sc3xIIII4s2s74x"
        bsize, btype, bvisior, bctime, bmtime, btimescale, bduration, brate, bvolume = struct.unpack(fmt, data)
        brate_h_int = int.from_bytes(brate[:2], byteorder='big', signed=False)
        brate_e_int = int.from_bytes(brate[2:], byteorder='big', signed=False)
        bvolume_h_int = int.from_bytes(bvolume[:1], byteorder='big', signed=False)
        bvolume_e_int = int.from_bytes(bvolume[1:], byteorder='big', signed=False)

        self._mvhd = {}
        self._mvhd["timescale"] = btimescale
        self._mvhd["duration"] = bduration 
        self._mvhd["rate"] = str(brate_h_int)+"."+str(brate_e_int) 
        self._mvhd["volume"] = str(bvolume_h_int)+"."+str(bvolume_e_int) 
        return  

    #获取trak中的的Mdia数据内容，并放入self._mdia中；moov->trak->mdia
    def getTrakMdia(self):

        for trakdata in self._trak:
            seek = 0
            while seek < len(trakdata):
                data = trakdata[seek:seek+8]
                dlen, dtype = struct.unpack(">I4s", data)
                if dtype == b"mdia":
                    self._mdia.append(trakdata[seek+8: seek+dlen])
                seek += dlen 

    #获取trak中的的Mdia数据内容，并放入self._mdia中；moov->trak->mdia->minf
    def getTrakMdiaMinf(self):

        for mdiadata in self._mdia:
            seek = 0
            avflag = None
            tmpdata = None
            while seek < len(mdiadata):
                data = mdiadata[seek:seek+8]
                dlen, dtype = struct.unpack(">I4s", data)           
                if dtype == b"minf":
                    tmpdata = mdiadata[seek+8: seek+dlen]
                if dtype == b"hdlr":
                    data1 = mdiadata[seek:seek+dlen]
                    dtype = struct.unpack(">16x4s"+str(dlen-20)+"x", data1)
                    avflag = dtype[0]                                     
                if avflag == b"vide" and tmpdata:
                    self._vminf.append(mdiadata[seek+8: seek+dlen])
                    avflag = ""
                if avflag == b"soun" and tmpdata:
                    self._aminf.append(mdiadata[seek+8: seek+dlen])
                    avflag = ""                     
                seek += dlen 

    #获取trak中的的Mdia数据内容，并放入self._mdia中；moov->trak->mdia->vminf->stbl
    def getTrakMdiaVMinfStbl(self):

        for vminfdata in self._vminf:
            seek = 0
            while seek < len(vminfdata):
                data = vminfdata[seek:seek+8]
                dlen, dtype = struct.unpack(">I4s", data)             
                if dtype == b"stbl":
                    self._vstbl.append(vminfdata[seek+8: seek+dlen])
                seek += dlen 

    #获取trak中的的Mdia数据内容，并放入self._mdia中；moov->trak->mdia->vminf->stbl->stss,stsc. stco
    def getTrakMdiaVMinfStblAll(self):

        for vstbldata in self._vstbl:
            seek = 0
            while seek < len(vstbldata):
                data = vstbldata[seek:seek+8]
                dlen, dtype = struct.unpack(">I4s", data)             
                if dtype == b"stss":
                    self._vstss.append(vstbldata[seek: seek+dlen])
                if dtype == b"stsc":
                    self._vstsc.append(vstbldata[seek: seek+dlen])   
                if dtype == b"stco":
                    self._vstco.append(vstbldata[seek: seek+dlen])
                if dtype == b"stsz":
                    self._vstsz.append(vstbldata[seek: seek+dlen])
                if dtype == b"stsd":
                    self._vstsd.append(vstbldata[seek: seek+dlen])                                                             
                seek += dlen 

    #获取SPS, PPS数据内容，并放入moov->trak->mdia->minf->stbl->avc1->avcC->sps pps
    #MP4的视频H264封装有2种格式：h264和avc1,在此先只实现avc1的内容解析，通过ffmpeg进行封装的基本都是avc1的格式
    def getMediaSpsPps(self):

        avccdata = None
        for vstsddata in self._vstsd:
            seek = 0
            while seek < len(vstsddata):
                data = vstsddata[seek:seek+8]
                dlen, dtype = struct.unpack(">I4s", data)
                if dtype == b"stsd":
                    avc1data = vstsddata[16: dlen]
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
                self.sps.append(sps)
                #这个值有可能算的不对，因为多循环的内容没有验证过；
                soffset = bsize_int+2
            pps_bt = avccdata[14+soffset:14+soffset+1]
            pps_num = int.from_bytes(pps_bt, byteorder="little", signed=False)
            soffset+=1
            for i in range(0, pps_num):
                bsize = avccdata[soffset+14:soffset+14+2]
                bsize_int = int.from_bytes(bsize, byteorder='big', signed=False)
                pps = avccdata[soffset+14+1:soffset+14+1+bsize_int]
                self.pps.append(sps)
                #这个值有可能算的不对，因为多循环的内容没有验证过；
                soffset += bsize_int+2                                    
        return                        

    #获取trak中的的Mdia数据内容，并放入self._mdia中；moov->trak->mdia->vminf->stbl
    def getTrakMdiaAMinfStbl(self):

        for aminfdata in self._aminf:
            seek = 0
            while seek < len(aminfdata):
                data = aminfdata[seek:seek+8]
                dlen, dtype = struct.unpack(">I4s", data)             
                if dtype == b"stbl":
                    self._astbl.append(aminfdata[seek+8: seek+dlen])
                seek += dlen 

    #获取trak中的的Mdia数据内容，并放入self._mdia中；moov->trak->mdia->vminf->stbl->stss,stsc. stco
    def getTrakMdiaAMinfStblAll(self):

        for astbldata in self._astbl:
            seek = 0
            while seek < len(astbldata):
                data = astbldata[seek:seek+8]
                dlen, dtype = struct.unpack(">I4s", data)             
                if dtype == b"stsc":
                    self._astsc.append(astbldata[seek: seek+dlen])   
                if dtype == b"stco":
                    self._astco.append(astbldata[seek: seek+dlen])
                if dtype == b"stsz":
                    self._astsz.append(astbldata[seek: seek+dlen])                                       
                seek += dlen 

    #获取视频中的关键帧的列表；从stcc中获取
    def getVideoKeyFrameList(self):

        #因为只有一个视频轨，所以只处理一个视频内容即可
        for vstssdata in self._vstss:
            data = vstssdata[:16]
            dlen, dary = struct.unpack(">I8xI", data)
            for i in range(0, dary, 1):
                h_int = int.from_bytes(vstssdata[16+i*4:16+i*4+4], byteorder='big', signed=False)
                self.keys.append(h_int)
            break

    #获取视频中的帧的大小；从stsz中获取
    def getVideoSampleSize(self):

        #因为只有一个视频轨，所以只处理一个视频内容即可
        for vstszdata in self._vstsz:
            data = vstszdata[:20]
            dary = struct.unpack(">16xI", data)
            for i in range(0, dary[0], 1):
                h_int1 = int.from_bytes(vstszdata[20+i*4:20+i*4+4], byteorder='big', signed=False)                              
                self.sample_size.append(h_int1)                
            break

    #获取视频中的帧的chunk列表；从stsc中获取
    def getVideoSampleChunk(self):

        #因为只有一个视频轨，所以只处理一个视频内容即可
        for vstscdata in self._vstsc:
            data = vstscdata[:16]
            dlen, dary = struct.unpack(">I8xI", data)
            o_chunk = 0
            o_num = 0
            for i in range(0, dlen, 12):
                #h_int1为取得的chunk的ID号，从1开始，为了保证后续的简单，把chunk的编号设为从0开始；
                h_int1 = int.from_bytes(vstscdata[16+i:16+i+4], byteorder='big', signed=False)
                h_int2 = int.from_bytes(vstscdata[16+i+4:16+i+8], byteorder='big', signed=False)
                
                sc = h_int1 - o_chunk - 1
                if sc > 1:
                    for h in range(0, sc, 1):
                        o_chunk += 1
                        for k in range(0, o_num):
                            self.chunks_samples.append(o_chunk)
                for k in range(0, h_int2):
                    self.chunks_samples.append(h_int1)
                o_chunk = h_int1
                o_num = h_int2  
            break

    #获取视频中的帧的每个chunk的偏移量；从stsc中获取
    def getVideoChunkOffset(self):

        #因为只有一个视频轨，所以只处理一个视频内容即可
        for vstcodata in self._vstco:
            data = vstcodata[:16]
            dlen, dary = struct.unpack(">I8xI", data)
            for i in range(0, dlen, 4):
                h_int1 = int.from_bytes(vstcodata[16+i:16+i+4], byteorder='big', signed=False)                              
                self.chunks_offset.append(h_int1)                
            break

    #获取音频中的帧的大小；从stsz中获取
    def getAudioSampleSize(self):

        #因为只有一个视频轨，所以只处理一个视频内容即可
        for astszdata in self._astsz:
            data = astszdata[:20]
            dary = struct.unpack(">16xI", data)
            for i in range(0, dary[0], 1):
                h_int1 = int.from_bytes(astszdata[20+i*4:20+i*4+4], byteorder='big', signed=False)                              
                self.asample_size.append(h_int1)                
            break

    #获取音频中的sample的chunk列表；从stsc中获取
    def getAudioSampleChunk(self):

        #只处理一个音频内容即可
        for astscdata in self._astsc:
            data = astscdata[:16]
            dlen, dary = struct.unpack(">I8xI", data)
            o_chunk = 0
            o_num = 0
            for i in range(0, dlen, 12):
                #h_int1为取得的chunk的ID号，从1开始，为了保证后续的简单，把chunk的编号设为从0开始；
                h_int1 = int.from_bytes(astscdata[16+i:16+i+4], byteorder='big', signed=False)
                h_int2 = int.from_bytes(astscdata[16+i+4:16+i+8], byteorder='big', signed=False)
                
                sc = h_int1 - o_chunk - 1
                if sc > 1:
                    for h in range(0, sc, 1):
                        o_chunk += 1
                        for k in range(0, o_num):
                            self.achunks_samples.append(o_chunk)
                for k in range(0, h_int2):
                    self.achunks_samples.append(h_int1)
                o_chunk = h_int1
                o_num = h_int2  
            break

    #获取音频中的帧的每个chunk的偏移量；从stsc中获取
    def getAudioChunkOffset(self):

        #因为只有一个视频轨，所以只处理一个视频内容即可
        for astcodata in self._astco:
            data = astcodata[:16]
            dlen, dary = struct.unpack(">I8xI", data)
            for i in range(0, dlen, 4):
                h_int1 = int.from_bytes(astcodata[16+i:16+i+4], byteorder='big', signed=False)                              
                self.achunks_offset.append(h_int1)                
            break

    #获取moov中trak的数据 trak为container box；
    def getTrakHeadTkhd(self, data):
        seek = 0
        fmt = ">I4sc3xIII4xI8x2s2x2s38xII"
        bsize, btype, bvisior, bctime, bmtime, btrackid, bduration, blayer, bvolume, bwidth, bheight = struct.unpack(fmt, data)
        bvolume_h_int = int.from_bytes(bvolume[:1], byteorder='big', signed=False)
        bvolume_e_int = int.from_bytes(bvolume[1:], byteorder='big', signed=False)

        self._mvhd = {}
        self._mvhd["timescale"] = btimescale
        self._mvhd["duration"] = bduration 
        self._mvhd["rate"] = str(brate_h_int)+"."+str(brate_e_int) 
        self._mvhd["volume"] = str(bvolume_h_int)+"."+str(bvolume_e_int) 
        return 

    #分析文件的头metadata信息是否在前面；
    def metaData_isFirst(self):
        self.seek = 0
        data = self._chunk[self.seek:self.seek+8]
        al = struct.unpack(">I4s", data)
        an = al[1].decode()

    def loadMetaData(self):
        self.getOneBoxData()
        self.getMoovData()
        self.getTrakMdia()
        self.getTrakMdiaMinf()
        self.getTrakMdiaVMinfStbl()
        self.getTrakMdiaVMinfStblAll()
        self.getTrakMdiaAMinfStbl()
        self.getTrakMdiaAMinfStblAll()      
        self.getVideoKeyFrameList()
        self.getVideoSampleChunk()
        self.getVideoChunkOffset()
        self.getVideoSampleSize()
        self.getAudioSampleChunk()    
        self.getAudioChunkOffset()
        self.getAudioSampleSize()
        self.getMediaSpsPps()        
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
        return


if __name__ == '__main__':

    metad = Mp4MetaData("http://10.10.10.101/lldq.mp4")
    start = datetime.datetime.now()
    metad.loadMetaData()           
    end = datetime.datetime.now()     
    print(str(end-start)+" 秒")
    start = datetime.datetime.now()
    metad.getFileOffsetByFrame(2)
    end = datetime.datetime.now()     
    print(str(end-start)+" 秒")  