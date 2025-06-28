// src/chatbot-widget.js

import React from "react";
import ReactDOM from "react-dom";
import ChatWidget from "./components/ChatWidget";
import "./components/ChatWidget.css"; // Widget styles
// UMD export: exposes HealthcareAIWidget.init(...)
const HealthcareAIWidget = {
  init: (userConfig) => {
    // Default configuration
    const config = {
      container: "#healthcare-ai-container",
      baseUrl: "http://localhost:9000",
      companyName: "AI Help Chat",
      companyLogo: "/logo.png",
      primaryColor: "#0066cc",
      showButton: true,
      showGreeting: false, // Disable greeting
      greetingText: "",
      introductionText: "",
      inputPlaceholder: "Ask about Stocks..",
      ...userConfig,
    };

    // Allow passing either a selector string or a DOM node
    const container =
      typeof config.container === "string"
        ? document.querySelector(config.container)
        : config.container;

    if (!container) {
      console.error(`Chatbot container not found: ${config.container}`);
      return;
    }

    // Create a button to open the chatbot if specified
    if (config.showButton !== false) {
      const buttonId = "healthcare-ai-button";
      let button = document.getElementById(buttonId);

      if (!button) {
        button = document.createElement("div");
        button.id = buttonId;
        button.className = "healthcare-ai-button";
        button.innerHTML = `
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"></path>
          </svg>
        `;
        document.body.appendChild(button);

        // Style the button
        Object.assign(button.style, {
          position: "fixed",
          bottom: "20px",
          right: "20px",
          width: "60px",
          height: "60px",
          borderRadius: "50%",
          backgroundColor: config.primaryColor || "#0066cc",
          color: "white",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: "pointer",
          boxShadow: "0 4px 8px rgba(0,0,0,0.2)",
          zIndex: "999",
        });

        // Add click event to open chatbot
        button.addEventListener("click", window.openChatbot);
      }
    }

    // Render the React ChatWidget, spreading all userConfig entries as props
    ReactDOM.render(<ChatWidget {...config} />, container);
  },
};

export default HealthcareAIWidget;

// Make chatbot opener available globally
if (typeof window !== "undefined") {
  window.openChatbot = function () {
    const chatbot = document.getElementById("chatbot");
    const button = document.getElementById("healthcare-ai-button");

    if (chatbot) {
      // First make sure it's visible (display block) before removing hidden class
      chatbot.style.display = "block";
      // Use requestAnimationFrame to ensure display change takes effect first
      requestAnimationFrame(() => {
        chatbot.classList.remove("hidden");
      });
    }

    if (button) button.style.display = "none";
  };
}
