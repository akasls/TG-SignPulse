"use client";

import { useEffect, useState } from "react";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Loader2, Play } from "lucide-react";
import { useToast } from "@/components/ui/use-toast";
import { format } from "date-fns";

interface Task {
    id: number;
    name: string;
    cron: string;
    enabled: boolean;
    last_run_at: string | null;
    account_id: number;
}

export default function AccountTasksPage() {
    const [tasks, setTasks] = useState<Task[]>([]);
    const [loading, setLoading] = useState(true);
    const { toast } = useToast();

    const fetchTasks = async () => {
        try {
            const res = await fetch("/api/tasks");
            if (!res.ok) throw new Error("Failed to fetch tasks");
            const data = await res.json();
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
            fetchTasks();
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
            <h1 className="text-3xl font-bold tracking-tight">Account Tasks</h1>
            <div className="rounded-md border bg-card/50 backdrop-blur">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>ID</TableHead>
                            <TableHead>Task Name</TableHead>
                            <TableHead>Cron</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Last Run</TableHead>
                            <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {tasks.map((task) => (
                            <TableRow key={task.id}>
                                <TableCell>{task.id}</TableCell>
                                <TableCell className="font-medium">{task.name}</TableCell>
                                <TableCell>{task.cron}</TableCell>
                                <TableCell>
                                    <Badge variant={task.enabled ? "default" : "secondary"}>
                                        {task.enabled ? "Active" : "Disabled"}
                                    </Badge>
                                </TableCell>
                                <TableCell>
                                    {task.last_run_at ? format(new Date(task.last_run_at), "PPpp") : "Never"}
                                </TableCell>
                                <TableCell className="text-right">
                                    <Button size="sm" variant="ghost" onClick={() => runTask(task.id)}>
                                        <Play className="w-4 h-4 mr-2" />
                                        Run
                                    </Button>
                                </TableCell>
                            </TableRow>
                        ))}
                        {tasks.length === 0 && (
                            <TableRow>
                                <TableCell colSpan={6} className="text-center h-24 text-muted-foreground">
                                    No tasks found.
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </div>
        </div>
    );
}
