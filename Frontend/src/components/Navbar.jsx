import React from "react";

export default function Navbar({ activeView, switchView }) {
  return (
    <nav className="bg-white border-b border-gray-200 px-8 py-3 flex justify-center items-center shadow-sm z-50">
      <div className="flex gap-1">
        <button
          onClick={() => switchView("chat")}
          className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all hover:bg-gray-100 ${
            activeView === "chat"
              ? "active-nav"
              : "text-gray-600"
          }`}
        >
          Chat General
        </button>
      </div>
    </nav>
  );
}