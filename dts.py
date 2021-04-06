#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2021-present, sun-shine cloud, Inc.
# All rights reserved
# video on demond to Stream (dts) 
# 是一个mp4点播文件转m3u8文件流和实时转换网关，主要是解决在视频处理过程中，
# 降低特定场景中视频协议转换的成本（如云环境下）；降低存储的成本，提升用户的体验（加载时间短）

from flask import Flask
from flask import request, Response, make_response
from flask import abort
from urllib.parse import unquote
from mp4Tools import mp4Tools
from hashlib import md5
import datetime
from mp4Parse import Mp4Parse
from mkM3u8List import mkM3u8List
from tsPack import tsPack
import logging_config

logger = logging_config.Config().get_config()

app = Flask(__name__)
 
@app.route("/dts.m3u8", methods=["GET", "POST"])         
#添加路由：dts是入口，参数为url=encode(http://1111/ssss/2222.mp4?ssss&ssss)
#该入口主要是提供实时的获取m3u8的列表，并返回点播的文件内容，其访问的TS文件的地址为：
# http://{BASE_URL}/ts/md5(url).ts?start=begin_frame&end=end_frame
# 其中BASE_URL在 mkM3u8List.py中定义，其为全局变量；此初始化内容可按实际要求更改；
def dts():

    url = None
    if request.method == "POST":
        url = request.form.get("url")
    else:
        url = request.args.get("url")
    if url == None:
        abort(404)
    try:
        start = datetime.datetime.now() 

        url1 = unquote(url)
        mp4_md5 = md5(url1.encode("utf8")).hexdigest() 

        mList = mkM3u8List(url1, mp4_md5)
        ret = mList.mk()

        end = datetime.datetime.now()     
        logger.info(str(end-start)+" 秒")    
        response = Response(ret)
        response.headers['Content-Type'] = "application/vnd.apple.mpegurl"
        # response.headers['Content-Disposition'] = "p_w_upload; filename="+mp4_md5+".m3u8"
        return response
    except:
        abort(503)

@app.route("/ts/<md5>.ts", methods=["GET"])
#此路由的定义是为了提供TS流和在实时封装和转换工作
def ts(md5):

    try:
        uri = request.path
        b_start = request.args.get("start")
        b_end = request.args.get("end")
        start = datetime.datetime.now() 
        tspack = tsPack(md5, int(b_start), int(b_end))
        ret_b = tspack.getTS()
        response = make_response(ret_b)
        # file = md5+".ts?start"+b_start+"&end="+b_end
        response.headers["Content-Type"] = "video/mp2t"
        # return response
        end = datetime.datetime.now()     
        logger.info(str(end-start)+" 秒") 
        return response
        # return Response(uri+b_start+b_end)
    except:
        abort(404)

if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=False)