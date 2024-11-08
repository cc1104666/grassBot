import asyncio
import random
import ssl
import json
import time
import uuid
from loguru import logger
from websockets_proxy import Proxy, proxy_connect


async def connect_to_wss(socks5_proxy, user_id):
    device_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, socks5_proxy))
    logger.info(f"设备ID: {device_id} 用户ID: {user_id}")
    while True:
        try:
            await asyncio.sleep(random.uniform(0.1, 1.0))
            custom_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            }
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            uri = "wss://proxy.wynd.network:4444/"
            proxy = Proxy.from_url(socks5_proxy)
            async with proxy_connect(uri, proxy=proxy, ssl=ssl_context, extra_headers={
                "Origin": "chrome-extension://lkbnfiajjmbhnfledhphioinpickokdi",
                "User-Agent": custom_headers["User-Agent"]
            }) as websocket:
                async def send_ping():
                    while True:
                        send_message = json.dumps(
                            {"id": str(uuid.uuid4()), "version": "1.0.0", "action": "PING", "data": {}})
                        logger.debug(f"发送PING以获取用户ID: {user_id}")
                        await websocket.send(send_message)
                        await asyncio.sleep(60)

                send_ping_task = asyncio.create_task(send_ping())
                try:
                    while True:
                        response = await websocket.recv()
                        message = json.loads(response)
                        logger.info(f"收到用户ID的消息 {user_id}: {message}")
                        if message.get("action") == "AUTH":
                            auth_response = {
                                "id": message["id"],
                                "origin_action": "AUTH",
                                "result": {
                                    "browser_id": device_id,
                                    "user_id": user_id,
                                    "user_agent": custom_headers['User-Agent'],
                                    "timestamp": int(time.time()),
                                    "device_type": "extension",
                                    "version": "4.20.2",
                                    "extension_id": "lkbnfiajjmbhnfledhphioinpickokdi"
                                }
                            }
                            logger.debug(f"发送用户ID的AUTH响应: {user_id}")
                            await websocket.send(json.dumps(auth_response))

                        elif message.get("action") == "PONG":
                            pong_response = {"id": message["id"], "origin_action": "PONG"}
                            logger.debug(f"发送用户ID的PONG响应: {user_id}")
                            await websocket.send(json.dumps(pong_response))
                finally:
                    send_ping_task.cancel()

        except Exception as e:
            logger.error(f"代理错误 {socks5_proxy} 用户ID {user_id}: {str(e)}")
            if any(error_msg in str(e) for error_msg in
                   ["[SSL:版本号错误]", "打包的IP地址字符串长度无效", "空连接回复",
                    "超出设备创建限制",
                    "发送1011（内部错误）保活ping超时；未收到闭合帧"]):
                logger.info(f"从列表中删除错误代理: {socks5_proxy}")
                return None
            else:
                await asyncio.sleep(5)
                continue


async def run_user_connections(user_id, all_proxies, num_connections):
    active_proxies = set()
    tasks = {}

    while True:
        while len(active_proxies) < num_connections and all_proxies:
            new_proxy = all_proxies.pop()
            active_proxies.add(new_proxy)
            new_task = asyncio.create_task(connect_to_wss(new_proxy, user_id))
            tasks[new_task] = new_proxy

        if not tasks:
            logger.warning(f"用户ID不再有可用的代理 {user_id}")
            break

        done, pending = await asyncio.wait(tasks.keys(), return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            proxy = tasks.pop(task)
            active_proxies.remove(proxy)
            if task.result() is None:
                logger.info(f"删除用户ID的代理失败 {user_id}: {proxy}")
            else:
                active_proxies.add(proxy)
                new_task = asyncio.create_task(connect_to_wss(proxy, user_id))
                tasks[new_task] = proxy

        await asyncio.sleep(1)


async def main():
    try:
        with open('id.txt', 'r') as file:
            user_ids = [line.strip() for line in file if line.strip()]

        if not user_ids:
            raise ValueError("在id.txt中找不到有效的用户id")

        with open('proxy.txt', 'r') as file:
            all_proxies = [line.strip() for line in file if line.strip()]

        if not all_proxies:
            raise ValueError("在proxy.txt中找不到有效的代理")

        total_connections = min(100, len(all_proxies))
        connections_per_user = max(1, total_connections // len(user_ids))

        logger.info(
            f"代理总数: {len(all_proxies)}, Users: {len(user_ids)}, 每个用户的连接数: {connections_per_user}")

        user_tasks = [run_user_connections(user_id, set(all_proxies), connections_per_user) for user_id in user_ids]
        await asyncio.gather(*user_tasks)

    except FileNotFoundError as e:
        logger.error(f"找不到文件: {e}")
    except ValueError as e:
        logger.error(f"配置错误: {e}")
    except Exception as e:
        logger.error(f"发生意外错误: {e}")


if __name__ == '__main__':
    asyncio.run(main())