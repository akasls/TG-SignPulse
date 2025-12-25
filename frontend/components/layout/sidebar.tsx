"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users, Settings, LogOut } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

{
    title: "Sign Tasks",
        href: "/dashboard/sign-tasks",
            icon: LayoutDashboard, // TODO: Find a better icon
    },
{
    title: "Account Tasks",
        href: "/dashboard/account-tasks",
            icon: LayoutDashboard, // TODO: Find a better icon
    },
{
    title: "Accounts",
        href: "/accounts",
            icon: Users,
    },
{
    title: "Settings",
        href: "/settings",
            icon: Settings,
    },
];

export function Sidebar() {
    const pathname = usePathname();

    return (
        <div className="flex flex-col h-full border-r bg-card/50 backdrop-blur-xl">
            <div className="p-6">
                <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-primary to-primary/50">
                    TG Signer
                </h1>
            </div>

            <nav className="flex-1 px-4 space-y-2">
                {sidebarItems.map((item) => {
                    const isActive = pathname.startsWith(item.href);
                    return (
                        <Link key={item.href} href={item.href}>
                            <Button
                                variant={isActive ? "secondary" : "ghost"}
                                className={cn(
                                    "w-full justify-start gap-2",
                                    isActive && "bg-secondary/50 font-semibold"
                                )}
                            >
                                <item.icon className="h-4 w-4" />
                                {item.title}
                            </Button>
                        </Link>
                    );
                })}
            </nav>

            <div className="p-4 border-t">
                <Button variant="ghost" className="w-full justify-start gap-2 text-muted-foreground hover:text-destructive">
                    <LogOut className="h-4 w-4" />
                    Logout
                </Button>
            </div>
        </div>
    );
}
