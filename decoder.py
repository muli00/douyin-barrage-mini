import base64
import gzip
from typing import Any, Dict, List

import douyin_pb2


def is_gzip(data: bytes) -> bool:
    """通过 gzip 魔数 (0x1f 0x8b) 判断数据是否经过 gzip 压缩。"""
    return len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B


def decode_frame(payload_b64: str) -> List[Dict[str, Any]]:
    """输入 CDP 返回的 Base64 字符串，输出清洗后的统一消息字典列表。"""
    raw_bytes = base64.b64decode(payload_b64)
    return decode_raw_bytes(raw_bytes)


def decode_raw_bytes(raw_bytes: bytes) -> List[Dict[str, Any]]:
    """输入原始 WebSocket 二进制帧字节流，输出清洗后的消息列表。"""
    frame = douyin_pb2.PushFrame()
    frame.ParseFromString(raw_bytes)
    if not frame.payload:
        return []

    payload = (
        gzip.decompress(frame.payload)
        if is_gzip(frame.payload)
        else frame.payload
    )

    response = douyin_pb2.Response()
    response.ParseFromString(payload)

    results: List[Dict[str, Any]] = []
    for msg in response.messagesList:
        parsed = _parse_message(msg.method, msg.payload)
        if parsed:
            results.append(parsed)
    return results


def _parse_message(method: str, payload: bytes) -> Dict[str, Any] | None:
    """根据消息 method 反序列化并归一化为统一 JSON 结构。"""
    if method == "WebcastChatMessage":
        m = douyin_pb2.ChatMessage()
        m.ParseFromString(payload)
        return {
            "type": "chat",
            "user_id": m.user.id,
            "nickname": m.user.nickName,
            "content": m.content,
        }

    if method == "WebcastGiftMessage":
        m = douyin_pb2.GiftMessage()
        m.ParseFromString(payload)
        return {
            "type": "gift",
            "user_id": m.user.id,
            "nickname": m.user.nickName,
            "gift_id": m.giftId,
            "gift_name": m.gift.name,
            "count": m.comboCount,
            "diamond": m.gift.diamondCount,
        }

    if method == "WebcastLikeMessage":
        m = douyin_pb2.LikeMessage()
        m.ParseFromString(payload)
        return {
            "type": "like",
            "user_id": m.user.id,
            "nickname": m.user.nickName,
            "count": m.count,
            "total": m.total,
        }

    if method == "WebcastMemberMessage":
        m = douyin_pb2.MemberMessage()
        m.ParseFromString(payload)
        return {
            "type": "member",
            "user_id": m.user.id,
            "nickname": m.user.nickName,
        }

    if method == "WebcastSocialMessage":
        m = douyin_pb2.SocialMessage()
        m.ParseFromString(payload)
        return {
            "type": "follow",
            "user_id": m.user.id,
            "nickname": m.user.nickName,
        }

    if method == "WebcastRoomStatsMessage":
        m = douyin_pb2.RoomStatsMessage()
        m.ParseFromString(payload)
        return {
            "type": "stats",
            "online_text": m.displayMiddle or m.displayShort,
            "online_count": m.displayValue,
        }

    return None
