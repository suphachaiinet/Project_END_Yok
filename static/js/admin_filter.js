// admin_filter.js - ไฟล์ JavaScript สำหรับฟิลเตอร์และการจัดการข้อมูลในหน้าแอดมิน

$(document).ready(function() {
    // ฟังก์ชันกลางสำหรับตาราง DataTables ที่ใช้ทั่วไป
    function initDataTable(tableId, options = {}) {
        // ค่าเริ่มต้นสำหรับตาราง DataTables
        const defaultOptions = {
            "language": {
                "url": "//cdn.datatables.net/plug-ins/1.10.24/i18n/Thai.json"
            },
            "pageLength": 25,
            "lengthMenu": [ [10, 25, 50, 100, -1], [10, 25, 50, 100, "ทั้งหมด"] ],
            "order": [[ 0, "asc" ]],
            "responsive": true,
            "dom": '<"top"Bfl>rt<"bottom"ip><"clear">',
            "buttons": [
                'copy', 'excel', 'pdf', 'print',
                {
                    text: 'ลบที่เลือกทั้งหมด',
                    className: 'btn-danger bulk-delete-btn',
                    action: function (e, dt, node, config) {
                        const selectedRows = dt.rows('.selected').data();
                        if (selectedRows.length === 0) {
                            alert('กรุณาเลือกรายการที่ต้องการลบ');
                            return;
                        }
                        
                        if (confirm(`คุณแน่ใจหรือไม่ที่จะลบรายการที่เลือกทั้งหมด ${selectedRows.length} รายการ?`)) {
                            // เก็บ ID ของแถวที่เลือก
                            const ids = [];
                            for (let i = 0; i < selectedRows.length; i++) {
                                ids.push(selectedRows[i][0]); // สมมติว่า ID อยู่ในคอลัมน์แรก
                            }
                            
                            // ส่งคำขอ AJAX เพื่อลบข้อมูล
                            $.ajax({
                                url: '/admin/bulk-delete',
                                type: 'POST',
                                data: {
                                    ids: ids.join(','),
                                    model: tableId // ใช้ ID ของตารางเพื่อระบุโมเดล
                                },
                                beforeSend: function(xhr) {
                                    // เพิ่ม CSRF token สำหรับ Django
                                    xhr.setRequestHeader("X-CSRFToken", $('input[name="csrfmiddlewaretoken"]').val());
                                },
                                success: function(response) {
                                    if (response.success) {
                                        alert('ลบข้อมูลเรียบร้อยแล้ว');
                                        // รีโหลดตาราง
                                        dt.ajax.reload();
                                    } else {
                                        alert('เกิดข้อผิดพลาด: ' + response.message);
                                    }
                                },
                                error: function(xhr, status, error) {
                                    alert('เกิดข้อผิดพลาดในการลบข้อมูล: ' + error);
                                }
                            });
                        }
                    }
                }
            ],
            "select": {
                style: 'multi',
                selector: 'td:first-child'
            },
            // เพิ่มคอลัมน์ checkbox สำหรับเลือกแถว
            "columnDefs": [
                {
                    "targets": 0,
                    "checkboxes": {
                        "selectRow": true
                    },
                    "width": "1%",
                    "className": "select-checkbox"
                }
            ]
        };

        // รวมตัวเลือกที่กำหนดเองกับค่าเริ่มต้น
        const mergedOptions = $.extend(true, {}, defaultOptions, options);
        
        // สร้างและคืนค่าอ็อบเจ็กต์ DataTable
        return $('#' + tableId).DataTable(mergedOptions);
    }

    // ตั้งค่าตาราง DataTables สำหรับหน้าต่าง ๆ
    
    // 1. ตาราง Users
    if ($("#userTable").length) {
        const userTable = initDataTable("userTable", {
            "columnDefs": [
                { "width": "1%", "targets": 0 },
                { "width": "10%", "targets": 1 },
                { "width": "15%", "targets": 2 },
                { "width": "15%", "targets": 3 },
                { "width": "7%", "targets": 4 },
                { "width": "10%", "targets": 5 },
                { "width": "15%", "targets": 6 },
                { "width": "15%", "targets": 7 },
                { "width": "12%", "targets": 8, "orderable": false }
            ],
            "order": [[ 1, "asc" ]]
        });

        // เพิ่มตัวกรองขั้นสูงสำหรับแต่ละคอลัมน์
        $("#userTable thead tr").clone(true).appendTo("#userTable thead");
        $("#userTable thead tr:eq(1) th").each(function (i) {
            const title = $(this).text();
            if (i > 0) { // ข้ามคอลัมน์ checkbox
                $(this).html('<input type="text" class="form-control form-control-sm" placeholder="ค้นหา ' + title + '" />');
                $("input", this).on("keyup change", function () {
                    if (userTable.column(i).search() !== this.value) {
                        userTable.column(i).search(this.value).draw();
                    }
                });
            } else {
                $(this).html('');
            }
        });

        // เพิ่มตัวกรองด่วนสำหรับสถานะและบทบาท
        $("#quick-filter-role").on("change", function() {
            userTable.column(4).search($(this).val()).draw();
        });

        $("#quick-filter-status").on("change", function() {
            userTable.column(5).search($(this).val()).draw();
        });
    }

    // 2. ตาราง Teachers
    if ($("#pendingTeachersTable").length) {
        const pendingTeachersTable = initDataTable("pendingTeachersTable", {
            "columnDefs": [
                { "width": "1%", "targets": 0 },
                { "width": "15%", "targets": 1 },
                { "width": "20%", "targets": 2 },
                { "width": "25%", "targets": 3 },
                { "width": "15%", "targets": 4 },
                { "width": "15%", "targets": 5, "orderable": false }
            ],
            "order": [[ 4, "desc" ]]
        });

        // เพิ่มตัวกรองสำหรับตารางอาจารย์รอการอนุมัติ
        $("#pendingTeachersTable thead tr").clone(true).appendTo("#pendingTeachersTable thead");
        $("#pendingTeachersTable thead tr:eq(1) th").each(function (i) {
            const title = $(this).text();
            if (i > 0 && i < 5) { // ข้ามคอลัมน์ checkbox และคอลัมน์ action
                $(this).html('<input type="text" class="form-control form-control-sm" placeholder="ค้นหา ' + title + '" />');
                $("input", this).on("keyup change", function () {
                    if (pendingTeachersTable.column(i).search() !== this.value) {
                        pendingTeachersTable.column(i).search(this.value).draw();
                    }
                });
            } else {
                $(this).html('');
            }
        });
    }

    if ($("#activeTeachersTable").length) {
        const activeTeachersTable = initDataTable("activeTeachersTable", {
            "columnDefs": [
                { "width": "1%", "targets": 0 },
                { "width": "15%", "targets": 1 },
                { "width": "20%", "targets": 2 },
                { "width": "25%", "targets": 3 },
                { "width": "15%", "targets": 4 },
                { "width": "15%", "targets": 5, "orderable": false }
            ],
            "order": [[ 1, "asc" ]]
        });

        // เพิ่มตัวกรองสำหรับตารางอาจารย์ที่อนุมัติแล้ว
        $("#activeTeachersTable thead tr").clone(true).appendTo("#activeTeachersTable thead");
        $("#activeTeachersTable thead tr:eq(1) th").each(function (i) {
            const title = $(this).text();
            if (i > 0 && i < 5) { // ข้ามคอลัมน์ checkbox และคอลัมน์ action
                $(this).html('<input type="text" class="form-control form-control-sm" placeholder="ค้นหา ' + title + '" />');
                $("input", this).on("keyup change", function () {
                    if (activeTeachersTable.column(i).search() !== this.value) {
                        activeTeachersTable.column(i).search(this.value).draw();
                    }
                });
            } else {
                $(this).html('');
            }
        });
    }

    // 3. ตาราง Students
    if ($("#studentsTable").length) {
        const studentsTable = initDataTable("studentsTable", {
            "columnDefs": [
                { "width": "1%", "targets": 0 },
                { "width": "15%", "targets": 1 },
                { "width": "20%", "targets": 2 },
                { "width": "25%", "targets": 3 },
                { "width": "15%", "targets": 4 },
                { "width": "15%", "targets": 5 },
                { "width": "10%", "targets": 6, "orderable": false }
            ],
            "order": [[ 1, "asc" ]]
        });

        // เพิ่มตัวกรองสำหรับตารางนักศึกษา
        $("#studentsTable thead tr").clone(true).appendTo("#studentsTable thead");
        $("#studentsTable thead tr:eq(1) th").each(function (i) {
            const title = $(this).text();
            if (i > 0 && i < 6) { // ข้ามคอลัมน์ checkbox และคอลัมน์ action
                $(this).html('<input type="text" class="form-control form-control-sm" placeholder="ค้นหา ' + title + '" />');
                $("input", this).on("keyup change", function () {
                    if (studentsTable.column(i).search() !== this.value) {
                        studentsTable.column(i).search(this.value).draw();
                    }
                });
            } else {
                $(this).html('');
            }
        });
    }

    // ฟังก์ชันช่วยสำหรับการทำงานกับวันที่
    $(".date-range-filter").on('cancel.daterangepicker', function(ev, picker) {
        $(this).val('');
        
        // ล้างการกรองวันที่
        const tableId = $(this).data('table');
        $.fn.dataTable.ext.search.pop();
        $('#' + tableId).DataTable().draw();
    });
    
    // ฟังก์ชันการลบข้อมูลจำนวนมาก
    $(".bulk-action-form").on("submit", function(e) {
        e.preventDefault();
        
        const selectedIds = [];
        const tableId = $(this).data('table');
        const action = $(this).find('select[name="action"]').val();
        
        // รวบรวม IDs ที่ถูกเลือก
        $('#' + tableId + ' tbody input[type="checkbox"]:checked').each(function() {
            selectedIds.push($(this).val());
        });
        
        if (selectedIds.length === 0) {
            alert('กรุณาเลือกรายการอย่างน้อย 1 รายการ');
            return;
        }
        
        // ตรวจสอบการกระทำ
        if (action === 'delete') {
            if (confirm(`คุณแน่ใจหรือไม่ที่จะลบรายการที่เลือกทั้งหมด ${selectedIds.length} รายการ?`)) {
                $.ajax({
                    url: $(this).attr('action'),
                    type: 'POST',
                    data: {
                        ids: selectedIds.join(','),
                        action: action,
                        model: $(this).data('model')
                    },
                    beforeSend: function(xhr) {
                        xhr.setRequestHeader("X-CSRFToken", $('input[name="csrfmiddlewaretoken"]').val());
                    },
                    success: function(response) {
                        if (response.success) {
                            alert('ดำเนินการเรียบร้อยแล้ว');
                            location.reload();
                        } else {
                            alert('เกิดข้อผิดพลาด: ' + response.message);
                        }
                    },
                    error: function() {
                        alert('เกิดข้อผิดพลาดในการดำเนินการ');
                    }
                });
            }
        } else if (action === 'approve' && tableId === 'pendingTeachersTable') {
            if (confirm(`คุณแน่ใจหรือไม่ที่จะอนุมัติอาจารย์ที่เลือกทั้งหมด ${selectedIds.length} คน?`)) {
                $.ajax({
                    url: '/admin/teachers/bulk-approve',
                    type: 'POST',
                    data: {
                        ids: selectedIds.join(',')
                    },
                    beforeSend: function(xhr) {
                        xhr.setRequestHeader("X-CSRFToken", $('input[name="csrfmiddlewaretoken"]').val());
                    },
                    success: function(response) {
                        if (response.success) {
                            alert('อนุมัติอาจารย์เรียบร้อยแล้ว');
                            location.reload();
                        } else {
                            alert('เกิดข้อผิดพลาด: ' + response.message);
                        }
                    },
                    error: function() {
                        alert('เกิดข้อผิดพลาดในการอนุมัติอาจารย์');
                    }
                });
            }
        }
    });
    
    // ปุ่มเลือกทั้งหมด
    $(".select-all-btn").click(function() {
        const tableId = $(this).data('table');
        $('#' + tableId + ' tbody input[type="checkbox"]').prop('checked', true);
    });
    
    // ปุ่มยกเลิกการเลือกทั้งหมด
    $(".deselect-all-btn").click(function() {
        const tableId = $(this).data('table');
        $('#' + tableId + ' tbody input[type="checkbox"]').prop('checked', false);
    });
    
    // สร้างฟิลเตอร์เมนูแบบด่วน
    $("#quick-filter-container").on("change", "select", function() {
        const column = $(this).data('column');
        const value = $(this).val();
        
        // ดึงตารางที่กำลังใช้งาน
        const tableId = $(this).closest('.quick-filter-form').data('table');
        const dataTable = $('#' + tableId).DataTable();
        
        if (value === '') {
            dataTable.column(column).search('').draw();
        } else {
            dataTable.column(column).search(value).draw();
        }
    });
    $(".date-range-filter").daterangepicker({
        autoUpdateInput: false,
        locale: {
            cancelLabel: 'ยกเลิก',
            applyLabel: 'ตกลง',
            format: 'DD/MM/YYYY'
        }
    });

    $(".date-range-filter").on('apply.daterangepicker', function(ev, picker) {
        $(this).val(picker.startDate.format('DD/MM/YYYY') + ' - ' + picker.endDate.format('DD/MM/YYYY'));
        
        // ดึง ID ของตารางที่เกี่ยวข้อง
        const tableId = $(this).data('table');
        const columnIndex = $(this).data('column');
        
        // ใช้ตัวกรองวันที่กับตาราง
        $.fn.dataTable.ext.search.push(
            function(settings, data, dataIndex) {
                if (settings.nTable.id !== tableId) {
                    return true;
                }
                
                const min = picker.startDate.format('YYYY-MM-DD');
                const max = picker.endDate.format('YYYY-MM-DD');
                const dateStr = data[columnIndex];
                
                if (dateStr === '' || dateStr === null) {
                    return false;
                }
                
                // แปลงรูปแบบวันที่จากตาราง (สมมติว่าอยู่ในรูปแบบ DD/MM/YYYY หรือ YYYY-MM-DD)
                let date;
                if (dateStr.includes('/')) {
                    const parts = dateStr.split('/');
                    date = new Date(parts[2], parts[1] - 1, parts[0]);
                } else {
                    date = new Date(dateStr);
                }
                
                const dateFormatted = date.toISOString().split('T')[0];
                
                return (min === null || min <= dateFormatted) &&
                       (max === null || max >= dateFormatted);
            }
        );
        
        // รีเฟรชตาราง
        $('#' + tableId).DataTable().draw();
    });

    $(".date-range-filter").on('cancel.daterangepicker', function(ev, picker) {
        $(this).val('');
        
        // ล้างการกรองวันที่
        const tableId = $(this).data('table');
        $.fn.dataTable.ext.search.pop();
        $('#' + tableId).DataTable().draw();
    });
    
    // ฟังก์ชันการลบข้อมูลจำนวนมาก
    $(".bulk-action-form").on("submit", function(e) {
        e.preventDefault();
        
        const selectedIds = [];
        const tableId = $(this).data('table');
        const action = $(this).find('select[name="action"]').val();
        
        // รวบรวม IDs ที่ถูกเลือก
        $('#' + tableId + ' tbody input[type="checkbox"]:checked').each(function() {
            selectedIds.push($(this).val());
        });
        
        if (selectedIds.length === 0) {
            alert('กรุณาเลือกรายการอย่างน้อย 1 รายการ');
            return;
        }
        
        // ตรวจสอบการกระทำ
        if (action === 'delete') {
            if (confirm(`คุณแน่ใจหรือไม่ที่จะลบรายการที่เลือกทั้งหมด ${selectedIds.length} รายการ?`)) {
                $.ajax({
                    url: $(this).attr('action'),
                    type: 'POST',
                    data: {
                        ids: selectedIds.join(','),
                        action: action,
                        model: $(this).data('model')
                    },
                    beforeSend: function(xhr) {
                        xhr.setRequestHeader("X-CSRFToken", $('input[name="csrfmiddlewaretoken"]').val());
                    },
                    success: function(response) {
                        if (response.success) {
                            alert('ดำเนินการเรียบร้อยแล้ว');
                            location.reload();
                        } else {
                            alert('เกิดข้อผิดพลาด: ' + response.message);
                        }
                    },
                    error: function() {
                        alert('เกิดข้อผิดพลาดในการดำเนินการ');
                    }
                });
            }
        } else if (action === 'approve' && tableId === 'pendingTeachersTable') {
            if (confirm(`คุณแน่ใจหรือไม่ที่จะอนุมัติอาจารย์ที่เลือกทั้งหมด ${selectedIds.length} คน?`)) {
                $.ajax({
                    url: '/admin/teachers/bulk-approve',
                    type: 'POST',
                    data: {
                        ids: selectedIds.join(',')
                    },
                    beforeSend: function(xhr) {
                        xhr.setRequestHeader("X-CSRFToken", $('input[name="csrfmiddlewaretoken"]').val());
                    },
                    success: function(response) {
                        if (response.success) {
                            alert('อนุมัติอาจารย์เรียบร้อยแล้ว');
                            location.reload();
                        } else {
                            alert('เกิดข้อผิดพลาด: ' + response.message);
                        }
                    },
                    error: function() {
                        alert('เกิดข้อผิดพลาดในการอนุมัติอาจารย์');
                    }
                });
            }
        }
    });
    
    // ปุ่มเลือกทั้งหมด
    $(".select-all-btn").click(function() {
        const tableId = $(this).data('table');
        $('#' + tableId + ' tbody input[type="checkbox"]').prop('checked', true);
    });
    
    // ปุ่มยกเลิกการเลือกทั้งหมด
    $(".deselect-all-btn").click(function() {
        const tableId = $(this).data('table');
        $('#' + tableId + ' tbody input[type="checkbox"]').prop('checked', false);
    });
    
    // สร้างฟิลเตอร์เมนูแบบด่วน
    $("#quick-filter-container").on("change", "select", function() {
        const column = $(this).data('column');
        const value = $(this).val();
        
        // ดึงตารางที่กำลังใช้งาน
        const tableId = $(this).closest('.quick-filter-form').data('table');
        const dataTable = $('#' + tableId).DataTable();
        
        if (value === '') {
            dataTable.column(column).search('').draw();
        } else {
            dataTable.column(column).search(value).draw();
        }
    });