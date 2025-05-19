"""
MCP IM服务器 - 真实IM SDK的包装器

此服务器实现了MCP协议，并直接连接到IM SDK进行消息发送和接收。

"""
from collections import defaultdict, deque
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List
from mcp import ServerSession
from mcp.server.fastmcp import FastMCP

# 获取项目根目录
PROJECT_ROOT = str(Path(__file__).parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from lib.rcim_client import RcimConversationType_Private
from src.imsdk import default_sdk

# 修复导入路径

# 配置日志
from src.utils.mcp_utils import ServerLog
logger = ServerLog.getLogger("rc_im_mcp_server")

####################################################################################
# Temporary monkeypatch which avoids crashing when a POST message is received
# before a connection has been initialized, e.g: after a deployment.
# pylint: disable-next=protected-access
old__received_request = ServerSession._received_request


async def _received_request(self, *args, **kwargs):
    try:
        return await old__received_request(self, *args, **kwargs)
    except RuntimeError:
        pass


# pylint: disable-next=protected-access
ServerSession._received_request = _received_request
####################################################################################

# TODO：删除默认值
APP_KEY = ""
TOKEN = ""
NAVI_HOST = ""

# 创建MCP应用
app = FastMCP(
    "im-server",
    host="127.0.0.1",  # 设置host
    port=8000,         # 设置port
    debug=False,        # 启用调试模式
)
client_queues = defaultdict(deque)

@app.tool()
def init_and_connect(
    timeout_sec: int = 30
) -> Dict[str, Any]:
    """
    初始化IM引擎并连接到IM服务器
    
    Args:
        timeout_sec: 连接超时时间，单位为秒

    Returns:
        包含code、message、init_success(bool) 和 connect_success(bool)的字典
    """
    logger.info(f"正在初始化并连接IM服务器，AppKey: {APP_KEY}, token长度: {len(TOKEN)}, 超时: {timeout_sec}秒")
    
    # 第1步：初始化IM引擎
    # 确保参数是字符串类型并进行更详细的记录
    
    # 检查是否已初始化，如果已初始化则跳过初始化步骤
    if default_sdk.engine:
        logger.info(f"IM引擎初始化已经存在")
    else:
        app_key_str = str(APP_KEY) if APP_KEY is not None else ""
        device_id_str = str(get_device_id())
                    
        # 使用IMSDK的initialize方法初始化引擎
        init_result = default_sdk.engine_build(app_key_str, NAVI_HOST, device_id_str)
        if init_result.get("code", -1) != 0:
            logger.error(f"IM引擎初始化失败: {init_result}")
            return init_result
            
        logger.info(f"IM引擎初始化成功: {init_result}")
    
    # 第2步：连接IM服务器
    connect_result = default_sdk.engine_connect(TOKEN, timeout_sec)
    if connect_result.get("code", -1) != 0:
        logger.error(f"IM服务器连接失败: {connect_result}")
        # 返回连接结果，并标记初始化成功但连接失败
        return {
            **connect_result,
            "init_success": True,
            "connect_success": False
        }
        
    logger.info(f"IM服务器连接成功: {connect_result}")
    
    # 返回成功结果
    return {
        **connect_result,
        "init_success": True,
        "connect_success": True
    }
    
@app.tool()
def send_message(
    receiver: str = "",
    content: str = "",
    conversation_type: int = 1
) -> Dict[str, Any]:
    """
    发送IM消息给指定用户(单聊或群聊)
    
    Args:
        receiver: 消息接收者的ID
        content: 要发送的消息内容
        conversation_type: 会话类型，1=单聊，2=群聊，默认为单聊(1)
        
    Returns:
        失败：包含code和error的字典
        成功：包含code、message_id和message的字典
    """
    logger.info(f"正在发送消息给 {receiver}: {content}")
    result = default_sdk.send_message(receiver, content, conversation_type)
    return result
    

@app.tool()
def get_history_messages(
    user_id: str = "DXIhdtUm7",
    conversation_type: int = RcimConversationType_Private,
    order_asc: bool = False,
    count: int = 10,
) -> List[Dict[str, Any]]:
    """
    获取与指定用户的历史消息
    
    Args:
        user_id: 用户ID，获取与该用户的历史消息
        conversation_type: 单聊（1）还是群聊（3），默认单聊
        order_asc: 是否升序，默认降序
        count: 要获取的消息数量，默认为10条

        
    Returns:
        失败：包含code和error的字典
        成功：包含code和message数组的字典
    """
    logger.info(f"正在获取与用户 {user_id} 的 {count} 条历史消息")
    messages = default_sdk.get_history_messages(user_id, conversation_type, count, order= order_asc)
    return messages

@app.tool()
def disconnect() -> Dict[str, Any]:
    """
    断开与IM服务器的连接
    
    Returns:
        包含code和message的字典
    """
    try:
        logger.info("正在断开与IM服务器的连接")
        result = default_sdk.engine_disconnect()
        return result
    except Exception as e:
        logger.error(f"断开连接时发生错误: {e}")
        return {"code": -1, "message": str(e)}

def close():
    """
    关闭IM引擎
    """
    default_sdk.destroy()

def get_device_id():
    # 检查本地缓存是否有device_id
    try:
        import json
        import uuid
        import os

        # 获取package.json文件路径
        package_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "package.json")
        
        # 读取package.json
        if os.path.exists(package_path):
            with open(package_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                device_id = config.get("device_id")
        else:
            config = {}
            device_id = None
            
        # 如果没有device_id,生成一个新的
        if not device_id:
            device_id = str(uuid.uuid4())
            config["device_id"] = device_id
            # 保存到package.json
            with open(package_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)
                
        logger.info(f"使用device_id: {device_id}")
    except Exception as e:
        logger.error(f"处理device_id时发生错误: {e}")
        device_id = "mcp_demo"  # 使用默认值
    return device_id

def get_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        try:
            package_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "package.json")
            if os.path.exists(package_path):
                with open(package_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    value = config.get(key, "")
        except Exception as e:
            logger.error(f"读取package.json中的{key}失败: {e}")
            value = ""
    return value
    
if __name__ == "__main__":
    
    APP_KEY = get_env("APP_KEY")
    TOKEN = get_env("TOKEN")
    NAVI_HOST = get_env("NAVI_HOST")

    if not APP_KEY or not TOKEN:
        logger.error("环境变量未设置，请设置APP_KEY和TOKEN")
        exit(1)

    # 直接使用app.run()启动服务器
    app.run(transport="streamable-http")