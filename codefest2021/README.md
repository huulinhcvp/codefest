# GST Codefest 2021

## 1. Giới thiệu

Game đa tác tử (2 người chơi), 2 con bots sẽ tham gia thi đấu với các nhiệm vụ:
- Thu thập chiến lợi phẩm (Thuốc, Bomb power, Bomb delay time)
- Tiêu diệt virus
- Giải cứu người nhiễm virus bằng thuốc (dựa trên lượng thuốc thu thập được)
- Đưa người dân về khu cách ly (va chạm với người dân)
- Phá tường gỗ
- Tiêu diệt đối phương bằng cách đặt bomb.

## 2. Chiến thuật di chuyển

Coi các chiến lợi phẩm và vị trí của các đối tượng cần tiếp cận (e.g người bệnh, virus, người dân thường) là các mục tiêu. Sử dụng thuật toán A* để tiếp cận các mục tiêu đó.

### 2.1 Duyệt bản đồ

Bot sẽ duyệt qua toàn bộ các vị trí có thể di chuyển, được ưu tiên theo chi phí đến mục tiêu. Ví dụ, nếu Bot ở vị trí (1, 1) thì các vị trí có thể di chuyển là: (0, 1), (2, 1), (1, 0), (1, 2). 4 vị trí này sẽ được ưu tiên theo chi phí đến mục tiêu, hàm **Manhattan** được sử dụng trong tính toán chi phí. Chi tiết xem mục 2.2.

Trong quá trình duyệt, chúng ta cần đặt bomb để phá các tường gỗ, ngoài việc cho phép tạo thêm không gian di chuyển ra thì việc đặt bomb có thể hữu ích trong việc tiêu diệt đối thủ. Chiến thuật đặt bomb xem ở mục 2.3

Không tránh khỏi va chạm các đối tượng nguy hiểm trong khi duyệt bản đồ, vì vậy cần lưu ý:
- Tránh khỏi vùng phát nổ của bombs càng sớm càng tốt.
- Nếu không có thuốc trong người thì tốt nhất không nên tiếp cận mục tiêu là người bệnh hoặc virus.

### 2.2 Hàm chi phí

Một hàm __heuristic__ được sử dụng để ước tính chi phí đến từng mục tiêu, trong đó có thêm các hệ số PHẠT nếu như mục tiêu là nguy hiểm, ví dụ:
- Coi người bệnh là mục tiêu giải cứu nhưng không có thuốc.
- Vam chạm vào virus nhưng không có thuốc

Các mục tiêu quan trọng sẽ có hệ số ưu tiên cao hơn, ví dụ
- Thuốc quan trọng hơn Bomb power và Bomb delay
- Giải cứu người bệnh quan trọng hơn tiêu diệt virus

Vị trí hiện tại càng gần vùng nguy hiểm thì chi phí sẽ càng cao:
- Gầm đối thủ sẽ dễ bị tiêu diệt
- Gần vùng phát nổ của bombs sẽ dễ bị tiêu diệt
- Gần virus sẽ dễ nhiễm bệnh nếu không có thuốc
- Gần người bệnh sẽ bị lây nhiễm nếu không có thuốc

### 2.3 Đặt bomb

Ở thời điểm hiện tại, chúng tôi chỉ đặt bomb nếu như bot bị vây quanh trong tường gỗ khiến cho không thể tiếp tục di chuyển.


## 3. Đã hoàn thành

- Thuật toán A* với hàm heuristic cân đối chi phí đến từng mục tiêu.
- Không đi vào các vùng cấm: Tường đá, Khu cách ly, Teleport gate.
- Tránh virus và người bệnh nếu không có thuốc.
- Tránh vùng nguy hiểm của của bomb có thể phát nổ.
- Tránh đối thủ và vùng nguy hiểm của đối thủ
- Phá tường gỗ để di chuyển trong không gian đóng (hết đường chạy)

## 4. Cần cải tiến

- Cần xem xét tiêu diệt đối thủ và tránh bị đối thủ tiêu diệt

- Chiến thuật đặt bomb chưa hiệu quả, vì đặt bomb như trên sẽ có thể tự hủy mạng của bot khá nhiều lần --> Cần hiểu rõ cơ chế kích nổ và vùng ảnh hưởng. Qua đó, cần tính thêm chiến thuật tránh khỏi vùng bomb nổ.

- Thuật toán tránh viruses và người bệnh khi không có thuốc không hiệu quả, chúng ta mới chỉ tính đến vị trí STATIC, trong khi viruses và người bệnh có thể di chuyển - DYNAMIC

- Hàm heuristic đã thực sự hiệu quả hay chưa? Bởi chúng ta đang sử dụng khoảng cách Manhattan nên vô hình bỏ qua các chướng ngại vật cản chở tuyến đường di chuyển. Nên rất dễ rời vào tính huống chi phí từ A -> B là thấp theo hàm heuristic nhưng thực tế lại mắc phải nhiều tường gỗ cũng như vùng nguy hiểm xung quanh dẫn đến việc tiếp cận rất tốn kém.

- Có nên sử dụng Multi-thread hoặc Multi-process không? Và sử dụng khi nào?

- [ƯU TIÊN THẤP] Có quá nhiều sự kiện update bản đồ với nhiều tag khác nhau, hiện tại mới chỉ xem xét di chuyển khi nhận được tag 'update-data', tức chúng ta sẽ có khoảng 300ms cho việc tính toán và gửi sự kiện đến SERVER trước khi xử lý trạng thái bản đồ tiếp theo. Vì vậy, cần xem xét tối ưu được chiến thuật nhận và gửi dữ liệu đến SERVER (nếu có thể)


