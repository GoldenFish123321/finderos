/**
 * base.js — 瞭望与问数系统基础脚本
 */

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
    console.log('瞭望与问数系统 v0.2 已启动');
});

/**
 * HTML 转义函数 —— 防止 DOM-based XSS
 * 将特殊字符转为 HTML 实体，确保用户输入不会被浏览器解析为 HTML/JS
 */
function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

/**
 * 通用列表页初始化器
 *
 * 通过配置对象统一处理分页、搜索、删除、toggle、消息提示等常见列表页逻辑。
 * 使用方式（在模板的 admin_scripts block 中）：
 *
 *   initListPage({
 *       url: '/admin/user',
 *       hasSearch: true,
 *       hasToggle: true,
 *       hasDelete: true,
 *       deleteConfirmText: '确定删除用户 <b>{name}</b> 吗？',
 *       total: {{ total }},
 *       page: {{ page }}
 *   });
 */
function initListPage(config) {
    var defaults = {
        url: '/admin/user',
        hasSearch: false,
        hasToggle: false,
        hasDelete: false,
        deleteConfirmText: '确定删除吗？',
        total: 0,
        page: 1
    };
    var cfg = Object.assign({}, defaults, config);

    var searchInput = document.getElementById('search-keyword');
    var searchBtn = document.getElementById('btn-search');
    var resetBtn = document.getElementById('btn-reset');
    var paginationEl = document.getElementById('pagination');

    function go(page, keyword) {
        var params = [];
        if (page && page > 1) params.push('page=' + page);
        if (keyword) params.push('keyword=' + encodeURIComponent(keyword));
        var qs = params.length ? '?' + params.join('&') : '';
        location.href = cfg.url + qs;
    }

    // 分页
    if (paginationEl) {
        layui.use(['laypage'], function(){
            var laypage = layui.laypage;
            laypage.render({
                elem: 'pagination',
                count: cfg.total || 0,
                limit: 20,
                curr: cfg.page || 1,
                groups: 5,
                layout: ['count', 'prev', 'page', 'next', 'skip'],
                jump: function(obj, first){
                    if(!first) go(obj.curr, searchInput ? searchInput.value : '');
                }
            });
        });
    }

    // 搜索（仅 hasSearch=true 时绑定）
    if (cfg.hasSearch && searchBtn) {
        searchBtn.addEventListener('click', function(){ go(1, searchInput.value); });
    }
    if (cfg.hasSearch && resetBtn) {
        resetBtn.addEventListener('click', function(){ location.href = cfg.url; });
    }
    if (cfg.hasSearch && searchInput) {
        searchInput.addEventListener('keydown', function(e){
            if(e.keyCode === 13 && searchBtn) searchBtn.click();
        });
    }

    // 通用操作（layer 弹层、删除、toggle、消息提示）
    layui.use(['layer'], function(){
        var layer = layui.layer;

        // 消息提示（对 msg 参数做 HTML 转义，防止 DOM-based XSS）
        var msg = new URLSearchParams(location.search).get('msg');
        if(msg) layer.msg(escapeHtml(msg), {icon: 1, time: 2000});

        // 删除
        if (cfg.hasDelete) {
            document.querySelectorAll('.btn-delete').forEach(function(btn){
                btn.addEventListener('click', function(){
                    var id = this.dataset.id;
                    var name = this.dataset.name || '';
                    var confirmText = cfg.deleteConfirmText.replace('{name}', name);
                    layer.confirm(confirmText, {
                        icon: 3,
                        title: '删除确认',
                        btn: ['确定删除', '取消']
                    }, function(){
                        document.getElementById('delete-id').value = id;
                        document.getElementById('form-delete').submit();
                    });
                });
            });
        }

        // toggle
        if (cfg.hasToggle) {
            document.querySelectorAll('.btn-toggle').forEach(function(btn){
                btn.addEventListener('click', function(){
                    document.getElementById('toggle-id').value = this.dataset.id;
                    document.getElementById('form-toggle').submit();
                });
            });
        }
    });
}
