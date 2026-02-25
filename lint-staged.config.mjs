export default {
  "*.{ts,tsx}": (files) => `eslint ${files.join(" ")}`,
};
