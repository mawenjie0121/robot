import requests
from tapdsdk.sdk import TapdAPIClient


class TAPDHandler:
    def __init__(self, client_id, client_secret):
        """
        初始化TAPD客户端
        :param client_id: 客户端ID
        :param client_secret: 客户端密钥
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.client = TapdAPIClient(
            client_id=client_id,
            client_secret=client_secret
        )

    def get_stories(self, params):
        """
        统一请求接口
        :param params: 符合图片中字段说明的查询参数
        """
        return self.client.get_stories(params)

    def get_bug_fields_info(self):
        return self.client.get_story_fields_info()

    def get_story_group_chat_info(self, workspace_id, story_id):
        url = "http://apiv2.tapd.woa.com/stories/get_story_group_chat_info"
        params = {
            "workspace_id": workspace_id,
            "story_id": story_id
        }
        auth = (self.client_id, self.client_secret)
        response = requests.get(url, params=params, auth=auth)
        response.raise_for_status()
        return response.json()
