"""ABaCAS Cloud 平台脚本公共模块：Token 读取 / API 头 / 常量"""
import os
import sys

BASE = 'https://cloud-test.abacas-dss.com/workflow-gateway/api'
BASE_INTERNAL = 'http://<内网IP>/workflow-gateway/api'  # 内网/n8n侧


def get_token(provided=None):
    """Token 优先级：--token 参数 > ABACAS_TOKEN 环境变量 > 当前目录 tmp_token.txt"""
    if provided:
        return provided
    t = os.environ.get('ABACAS_TOKEN')
    if t:
        return t.strip()
    if os.path.exists('tmp_token.txt'):
        return open('tmp_token.txt', encoding='utf-8').read().strip()
    sys.exit('错误: 未提供 Token。请用 --token 参数、设置 ABACAS_TOKEN 环境变量，或在工作目录放 tmp_token.txt。')


def headers(token):
    """API 请求头（注意：响应是 br 压缩，必须声明 Accept-Encoding 避免 requests 解码失败）"""
    return {'Authorization': 'Bearer ' + token, 'Accept-Encoding': 'gzip, deflate'}
