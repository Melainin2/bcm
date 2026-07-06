import React, { useEffect, useRef } from "react";
import Message from "./Message.jsx";

export default function ChatBox({ messages, loading, t }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div className="chatbox">
      {messages.length === 0 && !loading && (
        <div className="chat-empty">{t.empty}</div>
      )}
      {messages.map((m, i) => (
        <Message key={i} message={m} t={t} />
      ))}
      {loading && (
        <div className="message message-assistant">
          <div className="message-role">{t.assistant}</div>
          <div className="message-body typing">{t.sending}</div>
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
