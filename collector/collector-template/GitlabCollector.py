# coding:utf8
# author:winton

import logging
import os
import base64
import httplib
import json

from collector import Colllector


class GitlabCollector(Colllector):
    '''
    和gitlab相关的收集者，可以保存上一次的记录，支持增量处理
    '''
    def __init__(self, datapool, gitConfig):
        Colllector.__init__(self, datapool)
        self.hostname = gitConfig['hostname']
        self.port = gitConfig['port']

        self.repoId = gitConfig['repo_id']
        self.rootToken = gitConfig['root_token']
        self.ref = gitConfig['ref']
        self.headers = {}

        self.localRepo = gitConfig['localRepo']

    def readContent(self, filepath):
        '''
        从gitlab的指定路径下读取文件，如果文件不存在，返回None
        '''
        url = '/api/v3/projects/%(repo_id)d/repository/files?private_token=%(root_token)s&&file_path=%(filepath)s&&ref=%(ref)s' % {
            'repo_id': self.repoId,
            'root_token': self.rootToken,
            'filepath': filepath,
            'ref': self.ref
        }
        conn = httplib.HTTPConnection(self.hostname, self.port, timeout=30)
        content = None
        try:
            conn.request("GET", url, None, self.headers)
            response = conn.getresponse()
            if response.status == 200:
                response_data = response.read()
                response_data = json.loads(response_data)
                content = json.loads(base64.b64decode(response_data["content"]))
            elif response.status == 404:
                pass
            else:
                msg = json.loads(response.read())['message']
                logging.info('readContent: wrong status returned [msg=%s] [filepath=%s]' % (msg, filepath))
        except httplib.HTTPException as e:
            logging.warning('Exception when get file from remote repo [%s]' % str(e))
        finally:
            conn.close()
        return content

    def loadJsonFromLocalRepo(self, filepath):
        filepath = os.path.join(self.localRepo, filepath)
        logging.debug('loading flie in "%s"' % filepath)
        jsonData = self.loadJsonFromFile(filepath)
        return jsonData

    def getLastestConmit(self, perPage=100, page=0):
        '''
        获取最近的记录
        '''
        url = '/api/v3/projects/%(repo_id)d/repository/commits?private_token=%(root_token)s&ref_name=%(ref)s&page=%(page)d&%per_page=(perPage)d' % {
            'repo_id': self.repoId,
            'root_token': self.rootToken,
            'ref': self.ref,
            'page': page,
            'per_page': perPage,
        }
        conn = httplib.HTTPConnection(self.hostname, self.port, timout=30)
        commitsInfo = None
        try:
            conn.request('GET', url, None, self.headers)
            response = conn.getresponse()
            if response.status == 200:
                response_data = response.read()
                commitsInfo = json.loads(response_data)
            else:
                msg = json.loads(response.read())['message']
                logging.warning('wrong status when reading lastest commits [status=%d] [msg=%s]' % (response.status, msg))
        except httplib.HTTPException as e:
            logging.warning('Exception when get file from remote repo [%s]' % str(e))
        finally:
            conn.close()
        return commitsInfo

    def getCommitsAfterLastCommit(self, perPage=100, page=0):
        '''
        递归查询,获取上次commit以后的所有记录
        '''
        lastCommit = self.loadLastCommit()
        if not lastCommit:
            logging.warning('lastCommit not found, function returning...')
            raise Exception('lastCommit not found!')
        commitsInfo = self.getLastestConmit(perPage, page)
        lastCommitId = lastCommit['id']
        index = 0
        for commit in commitsInfo:
            index += 1
            if lastCommitId == commit['id']:
                logging.info('find last commit at index(%d), returning...' % index)
                return commitsInfo[:index]
        # 如果没有找到，就读取下一页继续找
        logging.info('didnt found, load next %d commits...' % perPage)
        return commitsInfo + self.getCommitsAfterLastCommit(perPage, page + 1)

    def saveLastCommit(self, commit):
        self.saveJsonToFile('last_commit.json', commit)

    def loadLastCommit(self):
        return self.loadJsonFromFile('last_commit.json')

    # TODO 处于对这个类的完整性考虑，需要实现一个读取每一条commit记录对应的文件的方法
    # 但是由于目前暂时不需要，所以暂不实现