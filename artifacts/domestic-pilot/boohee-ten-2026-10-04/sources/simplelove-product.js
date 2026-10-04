document.addEventListener('DOMContentLoaded', function() {
    // 假设 productData 已经在某个地方定义，或者通过 fetch 获取
    // 这里为了演示，我们直接使用 fetch 获取本地 json 文件
    // 注意：如果在本地直接打开 html 文件，fetch 可能会因为 CORS 策略失败，建议使用本地服务器
    
    const container = document.getElementById('productContainer');
    const modal = document.getElementById('productModal');
    const modalContent = document.querySelector('.modal-content');
    const closeBtn = document.querySelector('.close-btn');

    // 获取数据并渲染
    fetch('./data/product.json')
        .then(response => response.json())
        .then(data => {
            renderProducts(data);
        })
        .catch(error => console.error('Error loading product data:', error));

    function renderProducts(seriesList) {
        seriesList.forEach((series,index) => {
            // 1. 创建系列标题
            const titleEl = document.createElement('h2');
            titleEl.className = 'series-title';
            // 哈希
            titleEl.id = `series-${index+1}`;
            titleEl.textContent = series.name;
            container.appendChild(titleEl);

            // 2. 创建网格容器
            const gridEl = document.createElement('div');
            gridEl.className = 'product-grid';

            // 3. 遍历该系列下的产品
            series.list.forEach(product => {
                const card = document.createElement('div');
                card.className = 'product-card';
                
                // 存储产品数据以便点击时获取
                card.dataset.product = JSON.stringify(product);

                const imgWrapper = document.createElement('div');
                imgWrapper.className = 'card-img-wrapper';
                const img = document.createElement('img');
                img.src = product.img;
                img.alt = product.name;
                imgWrapper.appendChild(img);

                const nameEl = document.createElement('div');
                nameEl.className = 'card-name';
                nameEl.textContent = product.name;

                card.appendChild(imgWrapper);
                card.appendChild(nameEl);
                
                // 绑定点击事件
                card.addEventListener('click', () => openModal(product));

                gridEl.appendChild(card);
            });

            container.appendChild(gridEl);
        });

        // 页面链接后#标签对应的系列 页面滚动到和hash值一样的id位置
        const hash = window.location.hash;
        if (hash) {
            const element = document.getElementById(hash.slice(1));
            if (element) {
                // 滚动偏移100px
                window.scrollTo(0, element.offsetTop - 100, { behavior: 'smooth' });
                // element.scrollIntoView({ behavior: 'smooth' });
            }
        }
    }

    // 打开弹窗并填充数据
    function openModal(product) {
        document.getElementById('modalImg').src = product.img;
        document.getElementById('modalName').textContent = product.name;
        document.getElementById('modalIngredients').textContent = product.ingredients;

        const tbody = document.getElementById('modalTableBody');
        tbody.innerHTML = ''; // 清空旧数据

        product.component.forEach(item => {
            const tr = document.createElement('tr');

            tr.style = `opacity: ${item.option};`
            
            const tdName = document.createElement('td');
            tdName.textContent = item.name;
            
            const tdValue = document.createElement('td');
            tdValue.textContent = item.value;
            
            const tdPercentage = document.createElement('td');
            tdPercentage.textContent = item.percentage;

            tr.appendChild(tdName);
            tr.appendChild(tdValue);
            tr.appendChild(tdPercentage);
            tbody.appendChild(tr);
        });

        modal.style.display = 'block';
        modalContent.className = 'modal-content';
        document.body.style.overflow = 'hidden'; // 防止背景滚动

        trackEvent({
            eventType: 'button_click',
            eventName: `产品点击-${product.name}`,
        });
    }

    // 关闭弹窗
    function closeModal() {
        modal.style.display = 'none';
        modalContent.className = 'modal-content';
        document.body.style.overflow = 'auto'; // 恢复背景滚动
    }

    closeBtn.addEventListener('click', closeModal);

    // 点击弹窗外部也可关闭
    window.addEventListener('click', (event) => {
        if (event.target == modal) {
            closeModal();
        }
    });

    
});