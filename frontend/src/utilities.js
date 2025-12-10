export const API_BASE = "api";

export const makePaletteDraggable = (container) => {
    const checkExist = setInterval(() => {
        const palette = container.querySelector('.djs-palette');
        if (palette) {
            clearInterval(checkExist);
            if (!palette.querySelector('.palette-handle')) {
                const handle = document.createElement('div');
                handle.className = 'palette-handle';
                palette.prepend(handle);
                let isDragging = false;
                let startX, startY, initialLeft, initialTop;
                handle.addEventListener('mousedown', (e) => {
                    isDragging = true;
                    startX = e.clientX;
                    startY = e.clientY;
                    const rect = palette.getBoundingClientRect();
                    initialLeft = rect.left;
                    initialTop = rect.top;
                    e.preventDefault();
                });
                const onMouseMove = (e) => {
                    if (!isDragging) return;
                    const dx = e.clientX - startX;
                    const dy = e.clientY - startY;
                    palette.style.left = `${initialLeft + dx}px`;
                    palette.style.top = `${initialTop + dy}px`;
                    palette.style.right = 'auto';
                    palette.style.bottom = 'auto';
                };
                const onMouseUp = () => { isDragging = false; };
                document.addEventListener('mousemove', onMouseMove);
                document.addEventListener('mouseup', onMouseUp);
            }
        }
    }, 500);
};

export const getCurrentTime = () => {
    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const dd = String(now.getDate()).padStart(2, '0');
    const HH = String(now.getHours()).padStart(2, '0');
    const MM = String(now.getMinutes()).padStart(2, '0');
    const SS = String(now.getSeconds()).padStart(2, '0');
    return `${yyyy}/${mm}/${dd} ${HH}:${MM}:${SS}`;
};

export const formatTimelineTime = (fullTime) => {
    if (!fullTime) return '';
    const parts = fullTime.split(' ');
    if (parts.length === 2) {
        const dateParts = parts[0].split('/');
        if (dateParts.length === 3) {
            return `${dateParts[1]}/${dateParts[2]} ${parts[1]}`;
        }
    }
    return fullTime;
};

export const getLightHex = (hex, factor = 0.2) => {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);

    const newR = Math.round(r + (255 - r) * (1 - factor));
    const newG = Math.round(g + (255 - g) * (1 - factor));
    const newB = Math.round(b + (255 - b) * (1 - factor));

    const toHex = (n) => {
        const h = n.toString(16);
        return h.length === 1 ? '0' + h : h;
    };

    return `#${toHex(newR)}${toHex(newG)}${toHex(newB)}`;
};
