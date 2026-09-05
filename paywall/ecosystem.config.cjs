module.exports = {
  apps: [
    {
      name: "creatoros-paywall",
      cwd: __dirname,
      script: "index.js",
      interpreter: "node",
      instances: 1,
      exec_mode: "fork",
      env: {
        PORT: "8000",
        NODE_ENV: "production",
      },
    },
  ],
};
