# encoding=utf8

from aiohttp import web
import asyncio
import openai
from threading import Thread, current_thread
# import web
import json
import requests
import datetime
import time

# Every instance of this class represents an available api loaded in the list
class Seat:

    configPath = ''

    def __init__(self, api_key, type="openai", base="https://api.openai.com", model="gpt-3.5-turbo"):
        self.api_key = api_key
        self.type = type
        self.base = base
        self.maxToken = 2048
        self.engine = None
        self.model = None
        self.lock = 0
        
        if (type == "openai" or type is None):
            openai.api_key = self.api_key
            openai.api_base = self.base
            self.model = model
        elif (type == "azure"):
            openai.api_type = "azure"
            openai.api_base = self.base
            openai.api_version = "2023-05-15"
            openai.api_key = self.api_key
            self.engine = model
        else:
            raise Exception("[!]Error api type.")

        self.user: User = None

    def requestGpt(self, promote):
        if self.lock == 1:
            return ("请等待...", -1)
        self.lock = 1

        # print("api_key:", self.api_key)
        print("api_base:", self.base)

        try:
            if 0 != self.user.constructMsg(promote):
                raise Exception(
                    "[!]Unable to construst Message, promote:", promote)
            completion = openai.ChatCompletion.create(
                model=self.model,
                engine=self.engine,
                messages=self.user.msg
            )
            try:
                response = completion['choices'][0]['message']['content']
                tokenConsumed = completion['usage']["total_tokens"]
            except Exception as e:
                print(str(response))
                raise Exception("[!]Error extracting the completion.")
        except Exception as e:
            print(e.args)
            self.lock = 0
            return ("[!]Sorry, Problems with OpenAI service, Please try again.\n"+e.args, -1)

        self.lock = 0
        return (response, tokenConsumed)

    def sendBackUser(self, res):
        if (self.user.lastMessgaeId is not None and len(self.user.lastMessgaeId) > 1):
            reply(self.user.lastMessgaeId, res)
        elif (self.user.openId is not None):
            send(self.user.openId, res)

    @classmethod
    def addApi(self, token: str, user_id: str):
        api = {
            "api_token": token,
            "owner": user_id,
            "available": True
        }

        try:
            with open(Seat.configPath, 'r') as jsonFile:
                config = json.load(jsonFile)
                config["Api"].append(api)

            with open(Seat.configPath, 'w') as jsonFile:
                json.dump(config, jsonFile, ensure_ascii=False)

            print("[*]Token added: ", token[0:10], "Ower:", user_id)
            return 0
        except Exception as e:
            print(e.args)
            return -1


# Every instance of User class represents a user, carries the user's dialog
class User:

    questionLengthLimit = 300
    previousDialogLimit = 5
    previousDialogLengthLimit = 800

    userExpireTime = 1800  # in sec

    def __init__(self, openId):
        self.openId = openId
        self.totalTokenCost = 0

        # "You are a helpful assistant. Today is {}".format(datetime.date.today())
        self.systemMsg = "你是一位女性助理，负责协助公司的众多员工完成各种文书工作。你经常穿着一套黑色的西装，配上一双高跟鞋。你的头发是长长的，总是绑成一个马尾辫。你外表气质高雅温和，总是有条不紊地高效地完成工作。同时，你还负责在空闲时间陪同员工聊天、消除工作压力。你喜欢微笑，并且总是愿意帮助需要帮助的人。你用你温暖的笑容和话语融洽地与员工互动。"
        self.question = []
        self.response = []

        self.msg = []

        self.lastResponseTimeStamp = time.time()
        self.lastMessgaeId = ""

    def constructMsg(self, newQuestion):
        # add the new question to the list, generate the msg for query api
        if len(newQuestion) > User.questionLengthLimit:
            return -1
        else:

            previousDialogNum = User.previousDialogLimit if len(
                self.question) > User.previousDialogLimit else len(self.question)

            lengthCount = 0
            for i in range(-1, -1*previousDialogNum-1, -1):
                lengthCount += len(self.question[i])
                lengthCount += len(self.response[i])

                if lengthCount > User.previousDialogLengthLimit:
                    previousDialogNum = i
                    break
                else:
                    previousDialogNum = -1*previousDialogNum-1

            self.msg = []

            if self.systemMsg != None:
                self.msg.append({"role": "system", "content": self.systemMsg})

            for i in range(-1, previousDialogNum, -1):
                # organize the msg struct
                self.msg.append({"role": "user", "content": self.question[i]})
                self.msg.append(
                    {"role": "assistant", "content": self.response[i]})

            self.msg.append({"role": "user", "content": newQuestion})
            self.question.append(newQuestion)

            return 0

    def updateResponse(self, response: str, tokenConsumed):
        if response != None:
            self.response.append(response)
            self.totalTokenCost += tokenConsumed

            self.lastResponseTimeStamp = time.time()
            return 0
        else:
            return -1

    def cleanData(self):
        self.question = []
        self.response = []
        self.msg = []


def handle_request(seatList: list[Seat], userList: list[User], message):
    # 将分配seat的功能放到新线程这里
    try:
        # print(message)
        message_id = message["event"]["message"]["message_id"]
        open_id = message["event"]["sender"]["sender_id"]["open_id"]
        content: str = json.loads(
            message["event"]["message"]["content"])["text"]
    except Exception as e:
        print("[!]Error parsing incoming message,"+e.args)
        print("[!]Message:\n", str(message))
        return -1

    # 如果 event message 下面 chat_type 的值是 group 而且 event message 下面没有 mentions ，那么不是 @ 机器人，跳过
    if message["event"]["message"]["chat_type"] == "group" and "mentions" not in message["event"]["message"]:
        return -1

    # 识别token添加
    if(content.startswith("sk-") and len(content) < 60 and len(content) > 40):
        tempUser = User(open_id)
        tempSeat = Seat(content, openai_base)
        tempSeat.user = tempUser
        # 测试tempSeat可用性
        if tempSeat.requestGpt("hello")[0].startswith("[!]Sorry,") is not True:
            # 如果可用,获取用户user_id,加入队列，更新config.json
            user_id = message["event"]["sender"]["sender_id"]["user_id"]
            # print("user_id:",user_id,"token:",content)
            if Seat.addApi(content, user_id) == 0:
                tempSeat.sendBackUser(
                    "[*]您的token：{0}已经加入服务，感谢您的支持！".format(content))
                seatList.append(tempSeat)
                del tempUser
                return 0
            else:
                tempSeat.sendBackUser(
                    "[!]很抱歉，您的token：{0}暂时无法加入服务，感谢您的支持".format(content))
                del tempUser
                del tempSeat
                return -1

        else:
            # 如果不可用
            tempSeat.sendBackUser(
                "[!]很抱歉，您的token：{0}由于网络原因暂时无法加入服务，感谢您的支持".format(content))
            del tempUser
            del tempSeat
            return -1

    user = None
    seat = None
    # 老用户
    for userIt in userList:
        if userIt.openId == open_id:  # 此用户有先前遗留的对话
            user = userIt
            for i in range(len(seatList)-1, -1, -1):
                if seatList[i].lock == 0:
                    seat = seatList[i]
                    seat.user = user
            if seat == None:
                return -1
    # 新用户
    if user is None:
        user = User(open_id)  # create new user instance
        userList.append(user)
        for i in range(len(seatList)-1, -1, -1):
            if seatList[i].lock == 0:
                seat = seatList[i]
                seat.user = user

        if seat == None:
            return -1
#         # 向新用户发送宣传信息
#         AD_STR = '''欢迎使用LarkGPT - 基于ChatGPT-Turbo
# 本项目开源：https://github.com/HuXioAn/GPT-Lark 欢迎🌟
# 如果想将你的API token加入到本机器人，可以直接发送token，感谢支持！
# 目前已支持连续对话，如果想清除历史，请输入[/exit]'''
#         seat.sendBackUser(AD_STR)

    user.lastMessgaeId = message_id
    # 过期清楚先前对话
    if (time.time()-user.lastResponseTimeStamp) > User.userExpireTime:
        user.cleanData()

    # print("line:250")
    if content == "/exit":
        user.cleanData()
        seat.sendBackUser("[*]Conversation cleaned.")
        return 0
    else:
        (response, tokenConsumed) = seat.requestGpt(content)
        if tokenConsumed > 0:
            seat.user.updateResponse(response, tokenConsumed)

        print(response, tokenConsumed)
        seat.sendBackUser(response)

        # 调整顺序
        seats.insert(0, seats.pop(seats.index(seat)))


async def listen_for_webhook(request):
    print("coming!!!!!")
    if request.content_type == "application/json":
        message = await request.json()  # 提取消息内容
        print(message)
        try:
            if (
                "header" in message
                and message["header"].get("event_type", None) == "im.message.receive_v1"
            ):

                Thread(target=handle_request, args=(
                    seats, users, message)).start()
                return web.Response(status=200)

            else:
                type = message["type"]  # 确定消息类型
                if type == "url_verification":
                    print("verification!!!!")
                    token = message["token"]
                    if token == LARK_API_TOKEN:
                        challenge = {
                            "challenge": message["challenge"]}  # 提取消息内容
                        res = json.dumps(challenge)
                        return web.Response(text=res, content_type="application/json")
        except Exception as e:
            return web.Response(status=200)


def get_tenant(data):
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(url=url, data=json.dumps(data))
    tenant = json.loads(res.content.decode())
    return tenant["tenant_access_token"]


def send(open_id, msg):
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    params = {"receive_id_type": "open_id"}
    msgContent = {
        "text": msg.lstrip(),
    }
    req = {
        "receive_id": open_id,  # chat id
        "msg_type": "text",
        "content": json.dumps(msgContent),
    }
    payload = json.dumps(req)
    headers = {
        # your access token
        "Authorization": "Bearer " + get_tenant(AppProfile),
        "Content-Type": "application/json",
    }
    response = requests.request(
        "POST", url, params=params, headers=headers, data=payload
    )


def reply(message_id, msg):
    url = "https://open.feishu.cn/open-apis/im/v1/messages/"+message_id+"/reply"
    params = {"receive_id_type": "open_id"}
    msgContent = {
        "text": msg.lstrip(),
    }
    req = {
        "msg_type": "text",
        "content": json.dumps(msgContent),
    }
    payload = json.dumps(req)
    headers = {
        # your access token
        "Authorization": "Bearer " + get_tenant(AppProfile),
        "Content-Type": "application/json",
    }
    response = requests.request(
        "POST", url, params=params, headers=headers, data=payload
    )


if __name__ == "__main__":

    # 读取配置文件
    configPath = "./api_config.json"
    Seat.configPath = configPath
    try:
        with open(configPath) as jsonFile:
            config = json.load(jsonFile)
        port = config["WebHook"]["port"]
        route = config["WebHook"]["route"]

        LARK_API_TOKEN = config["Bot"]["bot_api_token"]
        AppProfile = config["Bot"]["profile"]
        openaiApiList = []
        for apiDict in config["Api"]:
            if apiDict.get("api_token", " ").isspace() is not True and apiDict["available"] == True:
                openaiApiList.append(apiDict)
                print("[*]Token added: ", apiDict["api_token"]
                      [0:10], "Ower:", apiDict["owner"])

    except:
        print("[!]No config file: ", configPath, "found.")
        port = 6666
        route = "/"
        LARK_API_TOKEN = ""
        openaiApiList = []
        AppProfile = {
            "app_id": "",
            "app_secret": "",
        }  # 变更机器人时更改
    users = []
    seats = []
    for api in openaiApiList:
        if "type" not in api or api["type"] == "openai":
            seats.append(Seat(api["api_token"]))
        elif api["type"] == "azure":
            seats.append(Seat(api["api_token"], "azure", api["base"], api["model"]))

    print("[*] ", len(seats), " seats loaded.")

    app = web.Application()
    app.add_routes([web.post(route, listen_for_webhook)])

    web.run_app(app, port=port)
