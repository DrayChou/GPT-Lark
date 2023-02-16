from aiohttp import web
import asyncio
import openai
from threading import Thread, current_thread
# import web
import json
import requests


class Seat:
    numOfSeat = 0
    configPath = ''

    def __init__(self, api):
        self.api = api
        self.maxToken = 256
        self.engie = "text-davinci-003"
        self.lock = 0

        self.user = None

        Seat.numOfSeat += 1

    def requestGpt(self, promote):
        if self.lock == 1:
            return "请等待..."
        self.lock = 1
        openai.api_key = self.api
        try:
            response = (
                openai.Completion.create(
                    engine=self.engie,
                    prompt=promote,
                    max_tokens=self.maxToken,
                    n=1,
                    stop=None,
                    temperature=0.3,
                    request_timeout=30,
                )
                .get("choices")[0]
                .text
            )
        except Exception as e:
            print(e.args)
            self.lock = 0
            return "[!]Sorry, Problems with OpenAI service, Please try again."

        self.lock = 0
        return response

    def sendBackUser(self, res):
        if (self.user is not None):
            send(self.user, res)

    @classmethod
    def addApi(self,token:str,user_id:str):
        api = {
            "api_token": token,
            "owner": user_id,
            "available": True
        }

        try:
            with open(Seat.configPath) as jsonFile:
                config = json.load(jsonFile)
                config["Api"].append(api)
                json.dump(config, jsonFile, ensure_ascii=False)
            
            print("[*]Token added: ",token[0:10],"Ower:",user_id)
            return 0
        except:
            return -1
            












def handle_request(seatList, message):
    #将分配seat的功能放到新线程这里

    open_id = message["event"]["sender"]["sender_id"]["open_id"]
    content:str = json.loads(message["event"]["message"]["content"])["text"]

    #识别token添加
    if(content.startswith("sk-") and len(content)<60 and len(content)>40):
        tempSeat = Seat(content)
        tempSeat.user = open_id
        #测试tempSeat可用性
        if tempSeat.requestGpt("hello").startswith("[!]Sorry,") is not True:
            #如果可用,获取用户user_id,加入队列，更新config.json
            user_id = message["event"]["sender"]["sender_id"]["user_id"]
            #print("user_id:",user_id,"token:",content)
            if Seat.addApi(content,user_id) == 0:
                tempSeat.sendBackUser("[*]您的token：{0}已经加入服务，感谢您的支持！".format(content))
                seatList.append(tempSeat)
                return 0
            else:
                tempSeat.sendBackUser("[!]很抱歉，您的token：{0}暂时无法加入服务，感谢您的支持".format(content))
                return -1

        else:
            #如果不可用
            tempSeat.sendBackUser("[!]很抱歉，您的token：{0}暂时无法加入服务，感谢您的支持".format(content))
            del tempSeat
            return -1
        



    seat = None          
    #老用户                      
    for seatIt in seatList:
        if seatIt.user == open_id:#此用户有先前遗留的对话
            seat = seatIt
    #新用户
    if seat is None:
        seat = seatList[len(seatList)-1]
        seat.user = open_id
        #向新用户发送宣传信息
        AD_STR = '''欢迎使用LarkGPT - 基于OpenAI GPT 
本项目开源：https://github.com/HuXioAn/GPT-Lark 欢迎🌟    
如果想将你的API token加入到本机器人，可以直接发送token，感谢支持！'''
    
        seat.sendBackUser(AD_STR)
    
    #print("asking ai")
    # Get the response from OpenAI's GPT-3 API
    response = seat.requestGpt(content)
    #print("got msg from openai:", response)

    # Send the response back to the user
    seat.sendBackUser(response)

    #调整顺序
    seats.insert(0,seats.pop(seats.index(seat)))



async def listen_for_webhook(request):
    # print("coming!!!!!")
    if request.content_type == "application/json":
        message = await request.json()  # 提取消息内容
        #print(message)
        try:
            if (
                "header" in message
                and message["header"].get("event_type", None) == "im.message.receive_v1"
            ):
                
                Thread(target=handle_request, args=(seats, message)).start()
                return web.Response(status=200)
                
            else:
                type = message["type"]  # 确定消息类型
                if type == "url_verification":
                    # print("verification!!!!")
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
        "Authorization": "Bearer " + get_tenant(AppProfile),  # your access token
        "Content-Type": "application/json",
    }
    response = requests.request(
        "POST", url, params=params, headers=headers, data=payload
    )


if __name__ == "__main__":

    #读取配置文件
    configPath = "./api_config.json"
    Seat.configPath = configPath
    try:
        with open(configPath) as jsonFile:
            config = json.load(jsonFile)
        port = config["WebHook"]["port"]
        route = config["WebHook"]["route"]

        LARK_API_TOKEN = config["Bot"]["bot_api_token"]
        AppProfile = config["Bot"]["profile"]
        openaiKeyList=[]
        for apiDict in config["Api"]:
            if apiDict.get("api_token"," ").isspace() is not True and apiDict["available"] == True:
                openaiKeyList.append(apiDict["api_token"])
                print("[*]Token added: ",apiDict["api_token"][0:10],"Ower:",apiDict["owner"])

    except:
        print("[!]No config file: ",configPath,"found.")
        port = 6666
        route = "/"
        LARK_API_TOKEN = ""
        openaiKeyList = []
        AppProfile = {
            "app_id": "",
            "app_secret": "",
        }  # 变更机器人时更改

    seats = []
    for key in openaiKeyList:
        seats.append(Seat(key))

    print("[*] ",len(seats)," seats loaded.")

    app = web.Application()
    app.add_routes([web.post(route, listen_for_webhook)])

    web.run_app(app, port=port)



