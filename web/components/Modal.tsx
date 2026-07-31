"use client";

import { useRouter } from "next/navigation";

export default function Modal({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const close = () => router.back();

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/55" onClick={close} />
      <div className="relative mx-auto my-[6vh] max-h-[88vh] max-w-xl overflow-y-auto rounded-[10px] border border-border bg-surface p-6 shadow-lg">
        <button
          onClick={close}
          aria-label="Close"
          className="absolute right-4 top-3 cursor-pointer text-2xl leading-none text-muted hover:text-foreground"
        >
          &times;
        </button>
        {children}
      </div>
    </div>
  );
}
