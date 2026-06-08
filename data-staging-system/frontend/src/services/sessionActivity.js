let touchActivityCallback = null;

export const registerTouchActivity = (callback) => {
    touchActivityCallback = callback;
};

export const notifyApiActivity = () => {
    touchActivityCallback?.();
};
