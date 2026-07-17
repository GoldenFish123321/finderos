/**
 * gesture.js — 手势识别模块
 *
 * 使用 MediaPipe Hands CDN 实现实时手势识别。
 * 通过摄像头捕获画面，识别 3 种手势并通过 onGesture 回调通知。
 *
 * 支持手势（与数字员工交互）：
 *   VICTORY (剪刀手) → @天气 [当前城市] 查天气（城市由页面逻辑定位补全）
 *   FIST    (握拳)   → @随机音乐
 *   PALM    (手掌)   → @新闻聚合
 *
 * 使用方式：
 *   var gd = new GestureDetector({
 *       videoElement: document.getElementById('gesture-video'),
 *       onGesture: function(gesture) { console.log(gesture); }
 *   });
 *   gd.init().then(function() { gd.start(); });
 *
 * 依赖（需在 HTML 中提前加载）：
 *   <script src="https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js" crossorigin="anonymous"></script>
 *   <script src="https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js" crossorigin="anonymous"></script>
 */

var GestureDetector = (function() {
    'use strict';

    // 手势常量
    var GESTURES = {
        VICTORY: 'VICTORY',  // 剪刀手
        FIST: 'FIST',        // 握拳
        PALM: 'PALM',        // 手掌
        NONE: 'NONE'
    };

    // 手势 → 触发消息映射
    var GESTURE_MESSAGE_MAP = {
        VICTORY: '@天气',
        FIST: '@随机音乐',
        PALM: '@新闻聚合'
    };

    // 手指关键点索引
    var FINGER_TIPS = { thumb: 4, index: 8, middle: 12, ring: 16, pinky: 20 };
    var FINGER_PIPS = { thumb: 3, index: 6, middle: 10, ring: 14, pinky: 18 };

    /**
     * @param {Object} options
     * @param {HTMLVideoElement} options.videoElement  视频元素
     * @param {HTMLCanvasElement} [options.canvasElement] 可选叠加 canvas（用于绘制骨架）
     * @param {Function} options.onGesture  手势回调 function(gestureName)
     * @param {number} [options.cooldown=2500]  手势触发冷却时间（ms）
     * @param {number} [options.minConfidence=3]  连续帧数确认阈值
     */
    function GestureDetector(options) {
        options = options || {};
        this.videoElement = options.videoElement || null;
        this.canvasElement = options.canvasElement || null;
        this.onGesture = typeof options.onGesture === 'function' ? options.onGesture : function() {};
        this.cooldown = options.cooldown || 2500;
        this.minConfidence = options.minConfidence || 3;

        this.running = false;
        this._hands = null;
        this._camera = null;
        this._lastGestureTime = 0;
        this._gestureStreak = {};
        this._currentGesture = GESTURES.NONE;
        this._canvasCtx = null;
    }

    /**
     * 初始化 MediaPipe Hands
     * 返回 Promise，在 Hands 就绪时 resolve
     */
    GestureDetector.prototype.init = function() {
        var self = this;

        // 检查全局依赖
        if (typeof Hands === 'undefined') {
            return Promise.reject(new Error('MediaPipe Hands 未加载。请先加载 https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js'));
        }
        if (typeof Camera === 'undefined') {
            return Promise.reject(new Error('MediaPipe Camera Utils 未加载。请先加载 https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js'));
        }

        self._hands = new Hands({
            locateFile: function(file) {
                return 'https://cdn.jsdelivr.net/npm/@mediapipe/hands/' + file;
            }
        });

        self._hands.setOptions({
            maxNumHands: 1,
            modelComplexity: 1,
            minDetectionConfidence: 0.5,
            minTrackingConfidence: 0.5
        });

        self._hands.onResults(function(results) {
            self._onResults(results);
        });

        if (self.canvasElement) {
            self._canvasCtx = self.canvasElement.getContext('2d');
            // 清除初始画布
            self._clearCanvas();
        }

        return Promise.resolve();
    };

    /**
     * 启动摄像头并开始手势识别
     */
    GestureDetector.prototype.start = function() {
        var self = this;
        if (!self.videoElement) {
            console.error('[GestureDetector] videoElement 未设置');
            return;
        }
        if (self.running) return;
        self.running = true;

        self._camera = new Camera(self.videoElement, {
            onFrame: async function() {
                if (self._hands) {
                    try {
                        await self._hands.send({ image: self.videoElement });
                    } catch (e) {
                        console.warn('[GestureDetector] MediaPipe send error:', e);
                    }
                }
            },
            width: 640,
            height: 480
        });

        self._camera.start().catch(function(err) {
            console.error('[GestureDetector] 摄像头启动失败:', err);
            self.running = false;
        });
    };

    /**
     * 停止手势识别
     */
    GestureDetector.prototype.stop = function() {
        this.running = false;
        if (this._camera) {
            try { this._camera.stop(); } catch (e) {}
            this._camera = null;
        }
    };

    /**
     * 获取手势对应的触发消息
     */
    GestureDetector.prototype.getMessageForGesture = function(gesture) {
        return GESTURE_MESSAGE_MAP[gesture] || '';
    };

    /**
     * 获取支持的手势列表
     */
    GestureDetector.prototype.getSupportedGestures = function() {
        return [
            { name: 'VICTORY', label: '剪刀手', message: GESTURE_MESSAGE_MAP.VICTORY },
            { name: 'FIST', label: '握拳', message: GESTURE_MESSAGE_MAP.FIST },
            { name: 'PALM', label: '手掌', message: GESTURE_MESSAGE_MAP.PALM }
        ];
    };

    // ============================================================
    // 内部方法
    // ============================================================

    /**
     * MediaPipe onResults 回调
     */
    GestureDetector.prototype._onResults = function(results) {
        if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
            this._currentGesture = GESTURES.NONE;
            this._clearCanvas(); // 手部离开时清除骨架
            return;
        }

        var landmarks = results.multiHandLandmarks[0];
        var gesture = this._classifyGesture(landmarks);

        // 绘制骨架
        if (this._canvasCtx) {
            this._drawSkeleton(landmarks);
        }

        // 连续帧确认（防抖）
        if (gesture === GESTURES.NONE) {
            this._gestureStreak = {};
            this._currentGesture = GESTURES.NONE;
            return;
        }

        if (!this._gestureStreak[gesture]) {
            this._gestureStreak[gesture] = 1;
        } else {
            this._gestureStreak[gesture]++;
        }

        // 仅在连续多帧确认后触发
        if (this._gestureStreak[gesture] >= this.minConfidence &&
            gesture !== this._currentGesture) {
            this._currentGesture = gesture;

            // 冷却期检查
            var now = Date.now();
            if (now - this._lastGestureTime > this.cooldown) {
                this._lastGestureTime = now;
                this.onGesture(gesture);
            }
        }
    };

    /**
     * 基于 21 个手部关键点分类手势
     */
    GestureDetector.prototype._classifyGesture = function(landmarks) {
        // 检查四指（食指、中指、无名指、小指）状态
        var indexUp = this._isFingerExtended(landmarks, FINGER_TIPS.index, FINGER_PIPS.index);
        var middleUp = this._isFingerExtended(landmarks, FINGER_TIPS.middle, FINGER_PIPS.middle);
        var ringUp = this._isFingerExtended(landmarks, FINGER_TIPS.ring, FINGER_PIPS.ring);
        var pinkyUp = this._isFingerExtended(landmarks, FINGER_TIPS.pinky, FINGER_PIPS.pinky);

        var extendedCount = (indexUp ? 1 : 0) + (middleUp ? 1 : 0) +
                            (ringUp ? 1 : 0) + (pinkyUp ? 1 : 0);

        // 手掌：4 指全部伸展
        if (extendedCount >= 4) {
            return GESTURES.PALM;
        }

        // 握拳：4 指全部弯曲
        if (extendedCount <= 1) {
            return GESTURES.FIST;
        }

        // 剪刀手：食指和中指伸展，无名指和小指弯曲
        if (indexUp && middleUp && !ringUp && !pinkyUp) {
            return GESTURES.VICTORY;
        }

        return GESTURES.NONE;
    };

    /**
     * 判断单根手指是否伸展
     * 对于 index/middle/ring/pinky：当指尖 y 坐标 < PIP y 坐标时视为伸展
     */
    GestureDetector.prototype._isFingerExtended = function(landmarks, tipIdx, pipIdx) {
        // 指尖在 PIP 上方（y 值更小）表示手指伸展
        return landmarks[tipIdx].y < landmarks[pipIdx].y;
    };

    /**
     * 清除 canvas 骨架绘制
     */
    GestureDetector.prototype._clearCanvas = function() {
        var ctx = this._canvasCtx;
        var canvas = this.canvasElement;
        if (ctx && canvas) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
    };

    /**
     * 释放摄像头资源
     */
    GestureDetector.prototype.destroy = function() {
        this.stop();
        this._hands = null;
        this._clearCanvas();
        this._canvasCtx = null;
    };

    /**
     * 在 canvas 上绘制手部骨架（调试用）
     */
    GestureDetector.prototype._drawSkeleton = function(landmarks) {
        var ctx = this._canvasCtx;
        var canvas = this.canvasElement;
        if (!ctx || !canvas) return;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // 绘制关键点
        ctx.fillStyle = '#00FF88';
        for (var i = 0; i < landmarks.length; i++) {
            var x = landmarks[i].x * canvas.width;
            var y = landmarks[i].y * canvas.height;
            ctx.beginPath();
            ctx.arc(x, y, 4, 0, 2 * Math.PI);
            ctx.fill();
        }

        // 绘制连线
        var connections = [
            [0, 1], [1, 2], [2, 3], [3, 4],           // 拇指
            [0, 5], [5, 6], [6, 7], [7, 8],           // 食指
            [0, 9], [9, 10], [10, 11], [11, 12],      // 中指
            [0, 13], [13, 14], [14, 15], [15, 16],    // 无名指
            [0, 17], [17, 18], [18, 19], [19, 20],    // 小指
            [5, 9], [9, 13], [13, 17]                 // 掌骨
        ];

        ctx.strokeStyle = '#00FF88';
        ctx.lineWidth = 2;
        connections.forEach(function(conn) {
            var start = landmarks[conn[0]];
            var end = landmarks[conn[1]];
            if (start && end) {
                ctx.beginPath();
                ctx.moveTo(start.x * canvas.width, start.y * canvas.height);
                ctx.lineTo(end.x * canvas.width, end.y * canvas.height);
                ctx.stroke();
            }
        });
    };

    // 导出
    GestureDetector.GESTURES = GESTURES;
    GestureDetector.GESTURE_MESSAGE_MAP = GESTURE_MESSAGE_MAP;

    return GestureDetector;
})();
