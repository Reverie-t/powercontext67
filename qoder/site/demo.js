// 科研周报助手展示站点演示脚本

function nextDemoStep(stepNum) {
    // 隐藏所有面板
    document.querySelectorAll('.demo-panel').forEach(panel => {
        panel.classList.remove('active');
    });
    
    // 显示目标面板
    document.getElementById(`demo-step-${stepNum}`).classList.add('active');
    
    // 更新步骤按钮状态
    document.querySelectorAll('.demo-step').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-step="${stepNum}"]`).classList.add('active');
}

function resetDemo() {
    nextDemoStep(1);
}

// 绑定步骤按钮点击事件
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.demo-step').forEach(btn => {
        btn.addEventListener('click', () => {
            const stepNum = btn.dataset.step;
            nextDemoStep(parseInt(stepNum));
        });
    });
});
