module.exports = {
  apps: [
    {
      name: "apollo-chatbot-frontend",
      script: "npx",
      args: "serve -l 5000 frontend",
      watch: false,
      autorestart: true,
      max_restarts: 10,
      env: {
        NODE_ENV: "production",
      },
    },
  ],
};
