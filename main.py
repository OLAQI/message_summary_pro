import logging
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api.event.filter import event_message_type, EventMessageType, command
from astrbot.api.provider import ProviderRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from typing import List, Dict
import json
import os
import datetime
import requests

logger = logging.getLogger("astrbot")

@register("group_summary", "yourname", "一个群聊总结插件", "1.0.0")
class GroupSummaryPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.message_count = 0
        self.messages = []
      
        # 初始化定时器
        self.scheduler = AsyncIOScheduler()
        if self.config["summary_time"] == "每天固定时间":
            self.scheduler.add_job(self.send_daily_summary, 'cron', hour=int(self.config["fixed_send_time"].split(":")[0]), minute=int(self.config["fixed_send_time"].split(":")[1]))
        self.scheduler.start()

    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent) -> MessageEventResult:
        self.message_count += 1
        # 确保添加到 messages 列表中的元素是字符串
        self.messages.append(event.message_obj.raw_message)

        # 检查是否达到总结条件
        if self.message_count >= self.config["message_count"]:
            await self.send_summary(event)
            self.reset_counters()

        # 检查是否触发命令词
        if self.config["trigger_command"] in event.message_obj.raw_message:
            await self.send_summary(event)

        return event.plain_result("")

    async def send_summary(self, event: AstrMessageEvent):
        summary = await self.generate_summary(self.messages)
        weather_info = await self.get_weather(self.config["weather_location"])
        await event.send(f"群聊总结：\n{summary}\n当前地区天气：{weather_info}")

    async def generate_summary(self, messages: List[str]) -> str:
        # 使用LLM生成总结
        provider = self.context.get_using_provider()
        if provider:
            # 确保 messages 列表中的元素是字符串
            prompt = f"请根据以下群聊内容生成一个简洁的总结：\n{' '.join(messages)}"
            response = await provider.text_chat(prompt, session_id=event.session_id)
            return response.completion_text
        else:
            return "无法生成总结，请检查LLM配置。"

    def reset_counters(self):
        self.message_count = 0
        self.messages = []

    async def send_daily_summary(self):
        for group_id in self.context.groups:
            event = AstrMessageEvent(group_id=group_id, message_str="")
            await self.send_summary(event)

    @command("summary_help")
    async def summary_help(self, event: AstrMessageEvent):
        help_text = """总结插件使用帮助：
1. 自动总结：
   - 当群聊中达到配置的消息条数时，会自动发送总结。
   - 可以通过设置配置项 `message_count` 来调整触发总结的消息条数。

2. 定时总结：
   - 可以设置每天固定时间发送总结，配置项为 `summary_time`，格式为 HH:MM。
   - 如果设置为 `immediate`，则立即发送总结。

3. 触发命令：
   - 监听到配置的命令词时，会立即触发发送总结，配置项为 `trigger_command`。

4. 帮助信息：
   - /summary_help - 显示此帮助信息。
"""
        await event.send(help_text)

    async def get_weather(self, location: str) -> str:
        """获取天气信息"""
        api_key = self.config.get("amap_api_key", "")
        if not api_key:
            return "未配置高德天气API，请在管理面板中设置。"

        url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={location}&key={api_key}"
        response = requests.get(url)
        data = response.json()
        if data["status"] == "1":
            weather = data["lives"][0]["weather"]
            temperature = data["lives"][0]["temperature"]
            return f"{weather}，温度：{temperature}℃"
        else:
            return "无法获取天气信息，请检查配置。"
