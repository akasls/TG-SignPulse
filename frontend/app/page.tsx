"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import LoginForm from "../components/login-form";
import { getToken } from "../lib/auth";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    const token = getToken();
    if (token) {
      router.replace("/dashboard");
    }
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <LoginForm />
    </div>
  );
}


