"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getToken } from "../../../../lib/auth";
import {
    createSignTask,
    listAccounts,
    getAccountChats,
    AccountInfo,
    ChatInfo,
    SignTaskChat,
} from "../../../../lib/api";
import { Button } from "../../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../../components/ui/card";
import { Input } from "../../../../components/ui/input";
import { Label } from "../../../../components/ui/label";

export default function CreateSignTaskPage() {
    const router = useRouter();
    const [token, setLocalToken] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");

    // 表单数据
    const [taskName, setTaskName] = useState("");
    const [signAt, setSignAt] = useState("0 6 * * *");
    const [randomSeconds, setRandomSeconds] = useState(0);
    const [signInterval, setSignInterval] = useState(1);
    const [chats, setChats] = useState<SignTaskChat[]>([]);

    // 账号和 Chat 数据
    const [accounts, setAccounts] = useState<AccountInfo[]>([]);
    const [selectedAccount, setSelectedAccount] = useState("");
    const [availableChats, setAvailableChats] = useState<ChatInfo[]>([]);

    // 当前编辑的 Chat
    const [editingChat, setEditingChat] = useState<{
        chat_id: number;
        name: string;
        actions: any[];
        delete_after?: number;
        action_interval: number;
    } | null>(null);

    useEffect(() => {
        const t = getToken();
        if (!t) {
            router.replace("/");
            return;
        }
        setLocalToken(t);
        loadAccounts(t);
    }, [router]);

    const loadAccounts = async (t: string) => {
        try {
            const data = await listAccounts(t);
            setAccounts(data.accounts);
            if (data.accounts.length > 0) {
                setSelectedAccount(data.accounts[0].name);
                loadChats(t, data.accounts[0].name);
            }
        } catch (err: any) {
            setError(err.message || "加载账号失败");
        }
    };

    const loadChats = async (t: string, accountName: string) => {
        try {
            const chatsData = await getAccountChats(t, accountName);
            setAvailableChats(chatsData);
        } catch (err: any) {
            console.error("加载 Chat 失败:", err);
        }
    };

    const handleAccountChange = (accountName: string) => {
        setSelectedAccount(accountName);
        if (token) {
            loadChats(token, accountName);
        }
    };

    const handleAddChat = () => {
        setEditingChat({
            chat_id: 0,
            name: "",
            actions: [],
            action_interval: 1,
        });
    };

    const handleSaveChat = () => {
        if (!editingChat) return;

        if (editingChat.chat_id === 0) {
            setError("请选择一个 Chat");
            return;
        }

        if (editingChat.actions.length === 0) {
            setError("请至少添加一个动作");
            return;
        }

        // 验证每个动作的内容
        for (let i = 0; i < editingChat.actions.length; i++) {
            const action = editingChat.actions[i];
            if (action.action === 1 && !action.text) {
                setError(`动作 ${i + 1}: 发送文本需要填写文本内容`);
                return;
            }
            if (action.action === 2 && !action.dice) {
                setError(`动作 ${i + 1}: 发送骰子需要填写骰子表情（如 🎲）`);
                return;
            }
            if (action.action === 3 && !action.text) {
                setError(`动作 ${i + 1}: 点击按钮需要填写按钮文本`);
                return;
            }
            // action 4 和 5 不需要额外参数
        }

        setChats([...chats, editingChat]);
        setEditingChat(null);
        setError("");
    };

    const handleRemoveChat = (index: number) => {
        setChats(chats.filter((_, i) => i !== index));
    };

    const handleAddAction = () => {
        if (!editingChat) return;

        setEditingChat({
            ...editingChat,
            actions: [
                ...editingChat.actions,
                { action: 1, text: "" }, // 默认添加发送文本动作
            ],
        });
    };

    const handleUpdateAction = (index: number, field: string, value: any) => {
        if (!editingChat) return;

        const newActions = [...editingChat.actions];
        newActions[index] = { ...newActions[index], [field]: value };
        setEditingChat({ ...editingChat, actions: newActions });
    };

    const handleRemoveAction = (index: number) => {
        if (!editingChat) return;

        setEditingChat({
            ...editingChat,
            actions: editingChat.actions.filter((_, i) => i !== index),
        });
    };

    const handleSubmit = async () => {
        if (!token) return;

        if (!taskName) {
            setError("请输入任务名称");
            return;
        }

        if (!signAt) {
            setError("请输入签到时间");
            return;
        }

        if (chats.length === 0) {
            setError("请至少添加一个 Chat");
            return;
        }

        try {
            setLoading(true);
            setError("");

            await createSignTask(token, {
                name: taskName,
                sign_at: signAt,
                chats: chats,
                random_seconds: randomSeconds,
                sign_interval: signInterval,
            });

            setSuccess("任务创建成功！");
            setTimeout(() => {
                router.push("/dashboard/sign-tasks");
            }, 1500);
        } catch (err: any) {
            setError(err.message || "创建任务失败");
        } finally {
            setLoading(false);
        }
    };

    if (!token) {
        return null;
    }

    return (
        <div className="p-6">
            <div className="max-w-4xl mx-auto">
                <div className="mb-6">
                    <h1 className="text-2xl font-bold">创建签到任务</h1>
                    <p className="text-sm text-gray-500 mt-1">
                        配置自动签到任务的详细信息
                    </p>
                </div>

                {/* 错误和成功提示 */}
                {error && (
                    <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-red-700">
                        {error}
                        <button onClick={() => setError("")} className="ml-2 font-bold">×</button>
                    </div>
                )}
                {success && (
                    <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded text-green-700">
                        {success}
                    </div>
                )}

                {/* 基本信息 */}
                <Card className="mb-6">
                    <CardHeader>
                        <CardTitle>基本信息</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div>
                            <Label htmlFor="taskName">任务名称</Label>
                            <Input
                                id="taskName"
                                placeholder="例如: linuxdo_sign"
                                value={taskName}
                                onChange={(e) => setTaskName(e.target.value)}
                            />
                        </div>

                        <div>
                            <Label htmlFor="signAt">签到时间（CRON 表达式）</Label>
                            <Input
                                id="signAt"
                                placeholder="0 6 * * *"
                                value={signAt}
                                onChange={(e) => setSignAt(e.target.value)}
                            />
                            <p className="text-xs text-gray-500 mt-1">
                                例如: 0 6 * * * (每天早上 6:00)
                            </p>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <Label htmlFor="randomSeconds">随机延迟（秒）</Label>
                                <Input
                                    id="randomSeconds"
                                    type="number"
                                    value={randomSeconds}
                                    onChange={(e) => setRandomSeconds(parseInt(e.target.value) || 0)}
                                />
                            </div>

                            <div>
                                <Label htmlFor="signInterval">签到间隔（秒）</Label>
                                <Input
                                    id="signInterval"
                                    type="number"
                                    value={signInterval}
                                    onChange={(e) => setSignInterval(parseInt(e.target.value) || 1)}
                                />
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Chat 配置 */}
                <Card className="mb-6">
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <CardTitle>Chat 配置</CardTitle>
                            <Button onClick={handleAddChat} size="sm">
                                + 添加 Chat
                            </Button>
                        </div>
                    </CardHeader>
                    <CardContent>
                        {chats.length === 0 ? (
                            <div className="text-center py-8 text-gray-500">
                                暂无 Chat 配置，点击"添加 Chat"开始
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {chats.map((chat, index) => (
                                    <div key={index} className="p-3 bg-gray-50 rounded">
                                        <div className="flex items-center justify-between mb-2">
                                            <div className="font-medium">{chat.name || `Chat ${chat.chat_id}`}</div>
                                            <Button
                                                variant="destructive"
                                                size="sm"
                                                onClick={() => handleRemoveChat(index)}
                                            >
                                                删除
                                            </Button>
                                        </div>
                                        <div className="text-sm text-gray-600">
                                            Chat ID: {chat.chat_id} | 动作数: {chat.actions.length}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </CardContent>
                </Card>

                {/* Chat 编辑对话框 */}
                {editingChat && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                        <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
                            <CardHeader>
                                <CardTitle>配置 Chat</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                {/* Chat 选择 */}
                                <div>
                                    <Label>选择 Chat</Label>
                                    <select
                                        className="w-full p-2 border rounded"
                                        value={editingChat.chat_id}
                                        onChange={(e) => {
                                            const chatId = parseInt(e.target.value);
                                            const chat = availableChats.find(c => c.id === chatId);
                                            setEditingChat({
                                                ...editingChat,
                                                chat_id: chatId,
                                                name: chat?.title || chat?.username || "",
                                            });
                                        }}
                                    >
                                        <option value={0}>请选择...</option>
                                        {availableChats.map((chat) => (
                                            <option key={chat.id} value={chat.id}>
                                                {chat.title || chat.username || chat.first_name || `Chat ${chat.id}`}
                                            </option>
                                        ))}
                                    </select>
                                </div>

                                {/* 动作配置 */}
                                <div>
                                    <div className="flex items-center justify-between mb-2">
                                        <Label>动作序列</Label>
                                        <Button onClick={handleAddAction} size="sm">
                                            + 添加动作
                                        </Button>
                                    </div>

                                    {editingChat.actions.length === 0 ? (
                                        <div className="text-center py-4 text-gray-500 text-sm">
                                            暂无动作，点击"添加动作"开始
                                        </div>
                                    ) : (
                                        <div className="space-y-3">
                                            {editingChat.actions.map((action, index) => (
                                                <div key={index} className="p-3 bg-gray-50 rounded">
                                                    <div className="flex items-start gap-3">
                                                        <div className="flex-1 space-y-2">
                                                            <select
                                                                className="w-full p-2 border rounded text-sm"
                                                                value={action.action}
                                                                onChange={(e) => handleUpdateAction(index, "action", parseInt(e.target.value))}
                                                            >
                                                                <option value={1}>发送文本</option>
                                                                <option value={2}>发送骰子</option>
                                                                <option value={3}>点击按钮</option>
                                                                <option value={4}>AI 图片识别</option>
                                                                <option value={5}>AI 计算题</option>
                                                            </select>

                                                            {(action.action === 1 || action.action === 3) && (
                                                                <Input
                                                                    placeholder={action.action === 1 ? "输入要发送的文本" : "输入按钮文本"}
                                                                    value={action.text || ""}
                                                                    onChange={(e) => handleUpdateAction(index, "text", e.target.value)}
                                                                />
                                                            )}

                                                            {action.action === 2 && (
                                                                <Input
                                                                    placeholder="输入骰子表情（如 🎲）"
                                                                    value={action.dice || ""}
                                                                    onChange={(e) => handleUpdateAction(index, "dice", e.target.value)}
                                                                />
                                                            )}
                                                        </div>
                                                        <Button
                                                            variant="destructive"
                                                            size="sm"
                                                            onClick={() => handleRemoveAction(index)}
                                                        >
                                                            删除
                                                        </Button>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                {/* 其他配置 */}
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <Label htmlFor="deleteAfter">删除延迟（秒，可选）</Label>
                                        <Input
                                            id="deleteAfter"
                                            type="number"
                                            placeholder="不删除"
                                            value={editingChat.delete_after || ""}
                                            onChange={(e) => setEditingChat({
                                                ...editingChat,
                                                delete_after: e.target.value ? parseInt(e.target.value) : undefined,
                                            })}
                                        />
                                    </div>

                                    <div>
                                        <Label htmlFor="actionInterval">动作间隔（秒）</Label>
                                        <Input
                                            id="actionInterval"
                                            type="number"
                                            value={editingChat.action_interval}
                                            onChange={(e) => setEditingChat({
                                                ...editingChat,
                                                action_interval: parseInt(e.target.value) || 1,
                                            })}
                                        />
                                    </div>
                                </div>

                                {/* 按钮 */}
                                <div className="flex gap-2 pt-4">
                                    <Button
                                        variant="secondary"
                                        onClick={() => setEditingChat(null)}
                                        className="flex-1"
                                    >
                                        取消
                                    </Button>
                                    <Button
                                        onClick={handleSaveChat}
                                        className="flex-1"
                                    >
                                        保存
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                )}

                {/* 提交按钮 */}
                <div className="flex gap-3">
                    <Link href="/dashboard/sign-tasks" className="flex-1">
                        <Button variant="secondary" className="w-full">
                            取消
                        </Button>
                    </Link>
                    <Button
                        onClick={handleSubmit}
                        disabled={loading}
                        className="flex-1"
                    >
                        {loading ? "创建中..." : "创建任务"}
                    </Button>
                </div>
            </div>
        </div>
    );
}
