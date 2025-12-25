"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, Play, Trash2 } from "lucide-react";
import { useToast } from "@/components/ui/use-toast";
import { format } from "date-fns";
import { Badge } from "@/components/ui/badge";

interface Task {
    id: number;
    name: string;
    cron: string;
    enabled: boolean;
    last_run_at: string | null;
    account_id: number;
}

export default function SignTasksPage() {
    const [tasks, setTasks] = useState<Task[]>([]);
    const [loading, setLoading] = useState(true);
    const { toast } = useToast();

    const fetchTasks = async () => {
        try {
            const res = await fetch("/api/tasks");
            if (!res.ok) throw new Error("Failed to fetch tasks");
            const data = await res.json();
            // Filter tasks that might be considered "Sign Tasks" based on name or convention
            // For now, allow all tasks to be visible here as per user request for "functionality"
            setTasks(data);
        } catch (error) {
            toast({
                title: "Error",
                description: "Failed to load tasks",
                variant: "destructive",
            });
        } finally {
            setLoading(false);
        }
    };

    const runTask = async (id: number) => {
        try {
            const res = await fetch(`/api/tasks/${id}/run`, { method: "POST" });
            if (!res.ok) throw new Error("Failed to run task");
            toast({
                title: "Success",
                description: "Task started successfully",
            });
            fetchTasks(); // Refresh to update last run time
        } catch (error) {
            toast({
                title: "Error",
                description: "Failed to run task",
                variant: "destructive",
            });
        }
    };

    useEffect(() => {
        fetchTasks();
    }, []);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <Loader2 className="w-8 h-8 animate-spin" />
            </div>
        );
    }

    return (
        <div className="space-y-6 p-8">
            <div className="flex items-center justify-between">
                <h1 className="text-3xl font-bold tracking-tight">Sign Tasks</h1>
                <Button onClick={() => fetchTasks()}>Refresh</Button>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {tasks.map((task) => (
                    <Card key={task.id} className="hover:shadow-lg transition-shadow bg-card/50 backdrop-blur">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium">
                                {task.name}
                            </CardTitle>
                            <Badge variant={task.enabled ? "default" : "secondary"}>
                                {task.enabled ? "Active" : "Disabled"}
                            </Badge>
                        </CardHeader>
                        <CardContent>
                            <div className="text-2xl font-bold truncate mt-2">{task.cron}</div>
                            <p className="text-xs text-muted-foreground mt-1">
                                Last run: {task.last_run_at ? format(new Date(task.last_run_at), "PPpp") : "Never"}
                            </p>
                            <div className="flex items-center gap-2 mt-4">
                                <Button size="sm" className="w-full" onClick={() => runTask(task.id)}>
                                    <Play className="w-4 h-4 mr-2" />
                                    Run Now
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                ))}
            </div>
            {tasks.length === 0 && (
                <div className="text-center text-muted-foreground mt-10">
                    No sign tasks found.
                </div>
            )}
        </div>
    );
}
