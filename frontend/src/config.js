// src/config.js
const config = {
  companyName: "My Stocks AI",
  companyLogo: "/assets/images/stocks-ai-logo.png",
  agentName: "My Stocks AI Assistant",
  projectName: "My Stocks AI",
  chatUrl: "ws://150.241.244.252:9000/ws",
  phoneSubmitUrl: "http://150.241.244.252:9000/api/mobile",
  theme: {
    primaryColor: "#0066cc",
    secondaryColor: "#f0f0f0",
    backgroundColor: "#ffffff",
    textColor: "#333333",
  },
  // Customizable introductory message
  introductionText: `
### 👋 Welcome to My Stocks AI Assistant.
I can help you with stock market analysis, trends, and investment insights.
  `,
  // Suggested questions that will appear after assistant replies
  suggestedQuestions: [
    "Today's recommended stocks?",
    "Top gainers in India today?",
    "Nifty 50 performance today?",
    "Best long-term stocks in India?",
    "What are mutual funds?",
    "What is swing trading?",
    "How does a stock split work?",
    "Risks of stock investing?",
    "Books for stock market beginners?",
    "BSE vs NSE difference?",
    "How do interest rates affect stocks?",
    "What are blue-chip stocks?",
    "Best sectors to invest in now?",
    "How do global markets affect India?",
    "What is technical analysis?",
    "Common stock market scams?",
    "What are stock derivatives?"
  ],
  // Number of questions to show at a time (default: 3)
  showNumberOfQuestions: 3,
  inputPlaceholder: "Ask about stocks, market trends, or investment advice...",
};

export default config;
