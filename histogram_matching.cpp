/**
 * @file histogram_matching.cpp
 * @brief OpenCV C++ 直方图匹配（Histogram Matching）算法实现
 * @author OpenCV4 Tutorial
 * @date 2024
 * 
 * 功能说明：
 * 1. 计算图像的直方图 (calcHist)
 * 2. 比较两个直方图的相似度 (compareHist)
 * 3. 实现直方图匹配 - 将源图像直方图匹配到目标直方图
 * 4. 可视化直方图对比结果
 */

#include <opencv2/opencv.hpp>
#include <iostream>

using namespace cv;
using namespace std;

/**
 * @brief 绘制直方图到图像上
 * @param hist 直方图数据
 * @param histSize 直方图的箱子数量
 * @param histImage 输出直方图图像
 * @param color 直方图颜色
 */
void drawHistogram(const Mat& hist, int histSize, Mat& histImage, Scalar color) {
    // 直方图归一化到 0~histImage.rows
    normalize(hist, hist, 0, histImage.rows, NORM_MINMAX, -1, Mat());

    // 计算每个箱子的宽度
    int binWidth = cvRound((double)histImage.cols / histSize);

    // 绘制每个箱子
    for (int i = 0; i < histSize; i++) {
        rectangle(histImage, 
                  Point(i * binWidth, histImage.rows),
                  Point((i + 1) * binWidth, histImage.rows - cvRound(hist.at<float>(i))),
                  color, -1, 8, 0);
    }
}

/**
 * @brief 计算图像的直方图
 * @param image 输入图像（支持灰度图和彩色图）
 * @param channels 通道索引
 * @param mask 可选掩码
 * @return Mat 直方图
 */
Mat calculateHistogram(const Mat& image, const vector<int>& channels, const Mat& mask = Mat()) {
    Mat hist;
    int histSize = 256;  // 灰度级数
    
    // 直方图参数
    const float* range[] = { static_cast<const float*>(static_cast<void*>(new float[2]{0, 256})) };
    // 为了兼容性，使用正确的 API
    float hranges[] = {0, 256};
    const float* ranges[] = {hranges};
    
    // 计算直方图
    calcHist(&image, 1, channels.data(), mask, hist, 1, &histSize, ranges, true, false);
    
    // 释放临时数组
    delete[] range[0];
    
    return hist;
}

/**
 * @brief 通用直方图计算函数
 */
Mat computeHistogram(const Mat& image, int histSize = 256) {
    Mat hist;
    float range[] = {0, 256};
    const float* histRange = {range};
    
    // 转换为灰度图
    Mat gray;
    if (image.channels() == 3) {
        cvtColor(image, gray, COLOR_BGR2GRAY);
    } else {
        gray = image.clone();
    }
    
    calcHist(&gray, 1, 0, Mat(), hist, 1, &histSize, &histRange, true, false);
    
    return hist;
}

/**
 * @brief 绘制彩色直方图（针对 BGR 图像）
 */
Mat drawColorHistogram(const Mat& image, int histSize = 256) {
    // 分离通道
    vector<Mat> bgr_planes;
    split(image, bgr_planes);
    
    // 直方图参数
    float range[] = {0, 256};
    const float* histRange = {range};
    bool uniform = true;
    bool accumulate = false;
    
    Mat b_hist, g_hist, r_hist;
    
    calcHist(&bgr_planes[0], 1, 0, Mat(), b_hist, 1, &histSize, &histRange, uniform, accumulate);
    calcHist(&bgr_planes[1], 1, 0, Mat(), g_hist, 1, &histSize, &histRange, uniform, accumulate);
    calcHist(&bgr_planes[2], 1, 0, Mat(), r_hist, 1, &histSize, &histRange, uniform, accumulate);
    
    // 创建直方图显示图像
    int hist_w = 512;
    int hist_h = 400;
    int bin_w = cvRound((double)hist_w / histSize);
    
    Mat histImage(hist_h, hist_w, CV_8UC3, Scalar(0, 0, 0));
    
    // 归一化直方图到 [0, histImage.rows]
    normalize(b_hist, b_hist, 0, histImage.rows, NORM_MINMAX, -1, Mat());
    normalize(g_hist, g_hist, 0, histImage.rows, NORM_MINMAX, -1, Mat());
    normalize(r_hist, r_hist, 0, histImage.rows, NORM_MINMAX, -1, Mat());
    
    // 绘制每个通道的直方图
    for (int i = 0; i < histSize; i++) {
        line(histImage, 
             Point((i + 0) * bin_w, hist_h - cvRound(b_hist.at<float>(i))),
             Point((i + 1) * bin_w, hist_h - cvRound(b_hist.at<float>(i))),
             Scalar(255, 0, 0), 2, 8, 0);
        line(histImage,
             Point((i + 0) * bin_w, hist_h - cvRound(g_hist.at<float>(i))),
             Point((i + 1) * bin_w, hist_h - cvRound(g_hist.at<float>(i))),
             Scalar(0, 255, 0), 2, 8, 0);
        line(histImage,
             Point((i + 0) * bin_w, hist_h - cvRound(r_hist.at<float>(i))),
             Point((i + 1) * bin_w, hist_h - cvRound(r_hist.at<float>(i))),
             Scalar(0, 0, 255), 2, 8, 0);
    }
    
    return histImage;
}

/**
 * @brief 比较两个直方图并返回相似度
 */
double compareHistograms(const Mat& hist1, const Mat& hist2, int method = HISTCMP_CORREL) {
    return compareHist(hist1, hist2, method);
}

/**
 * @brief 打印直方图比较方法的结果
 */
void printComparisonResults(const Mat& hist1, const Mat& hist2, const string& name1, const string& name2) {
    cout << "\n========== 直方图比较结果 (" << name1 << " vs " << name2 << ") ==========" << endl;
    
    // 相关性 (Correlation): 1 表示完美匹配, 0 表示完全不匹配
    double corr = compareHist(hist1, hist2, HISTCMP_CORREL);
    cout << "相关性 (Correlation): " << corr << " (1=完美匹配, 0=完全不匹配)" << endl;
    
    // 卡方 (Chi-square): 0 表示完美匹配, 值越大匹配越差
    double chi = compareHist(hist1, hist2, HISTCMP_CHISQR);
    cout << "卡方 (Chi-square): " << chi << " (0=完美匹配)" << endl;
    
    // 交叉 (Intersection): 值越大表示越匹配
    double inter = compareHist(hist1, hist2, HISTCMP_INTERSECT);
    cout << "交叉 (Intersection): " << inter << " (值越大越匹配)" << endl;
    
    // Bhattacharyya 距离: 0 表示完美匹配, 1 表示完全不匹配
    double bhatt = compareHist(hist1, hist2, HISTCMP_BHATTACHARYYA);
    cout << "Bhattacharyya 距离: " << bhatt << " (0=完美匹配, 1=完全不匹配)" << endl;
    
    cout << "=============================================" << endl;
}

/**
 * @brief 直方图匹配 - 将源图像直方图转换为目标直方图
 * 实现步骤：
 * 1. 计算源图像和目标图像的直方图
 * 2. 计算源图像和目标图像的累积直方图 (CDF)
 * 3. 建立源 CDF 到目标 CDF 的映射
 * 4. 创建查找表 (LUT) 进行直方图匹配
 */
Mat histogramMatching(const Mat& src, const Mat& ref) {
    // 确保输入是灰度图
    Mat src_gray, ref_gray;
    if (src.channels() == 3) {
        cvtColor(src, src_gray, COLOR_BGR2GRAY);
    } else {
        src_gray = src.clone();
    }
    if (ref.channels() == 3) {
        cvtColor(ref, ref_gray, COLOR_BGR2GRAY);
    } else {
        ref_gray = ref.clone();
    }
    
    // 计算直方图
    int histSize = 256;
    float range[] = {0, 256};
    const float* histRange = {range};
    
    Mat src_hist, ref_hist;
    calcHist(&src_gray, 1, 0, Mat(), src_hist, 1, &histSize, &histRange, true, false);
    calcHist(&ref_gray, 1, 0, Mat(), ref_hist, 1, &histSize, &histRange, true, false);
    
    // 归一化直方图
    normalize(src_hist, src_hist, 0, 255, NORM_MINMAX);
    normalize(ref_hist, ref_hist, 0, 255, NORM_MINMAX);
    
    // 计算累积直方图 (CDF)
    Mat src_cdf(1, 256, CV_32FC1);
    Mat ref_cdf(1, 256, CV_32FC1);
    
    float src_sum = 0;
    float ref_sum = 0;
    for (int i = 0; i < 256; i++) {
        src_sum += src_hist.at<float>(i);
        ref_sum += ref_hist.at<float>(i);
        src_cdf.at<float>(i) = src_sum;
        ref_cdf.at<float>(i) = ref_sum;
    }
    
    // 归一化累积直方图
    src_cdf /= src_sum;
    ref_cdf /= ref_sum;
    
    // 建立映射表 (LUT)
    Mat lut(1, 256, CV_8UC1);
    for (int i = 0; i < 256; i++) {
        float src_val = src_cdf.at<float>(i);
        int j = 0;
        // 找到最接近的目标 CDF 值
        for (j = 0; j < 256 - 1; j++) {
            if (ref_cdf.at<float>(j + 1) >= src_val) {
                break;
            }
        }
        lut.at<uchar>(i) = j;
    }
    
    // 应用 LUT 进行直方图匹配
    Mat result;
    LUT(src_gray, lut, result);
    
    return result;
}

/**
 * @brief 手动实现直方图均衡化（用于对比）
 */
Mat manualEqualizeHist(const Mat& src) {
    Mat src_gray;
    if (src.channels() == 3) {
        cvtColor(src, src_gray, COLOR_BGR2GRAY);
    } else {
        src_gray = src.clone();
    }
    
    // 计算直方图
    int histSize = 256;
    float range[] = {0, 256};
    const float* histRange = {range};
    
    Mat hist;
    calcHist(&src_gray, 1, 0, Mat(), hist, 1, &histSize, &histRange, true, false);
    
    // 计算 CDF
    Mat cdf(1, 256, CV_32FC1);
    float cumsum = 0;
    for (int i = 0; i < 256; i++) {
        cumsum += hist.at<float>(i);
        cdf.at<float>(i) = cumsum;
    }
    
    // 归一化 CDF
    cdf /= cumsum;
    
    // 建立 LUT
    Mat lut(1, 256, CV_8UC1);
    for (int i = 0; i < 256; i++) {
        lut.at<uchar>(i) = cvRound(cdf.at<float>(i) * 255);
    }
    
    // 应用 LUT
    Mat result;
    LUT(src_gray, lut, result);
    
    return result;
}

/**
 * @brief 创建并排显示的对比图
 */
Mat createComparisonWindow(const Mat& img1, const Mat& img2, const Mat& img3, 
                           const string& title1, const string& title2, const string& title3) {
    Mat combined;
    
    // 调整图像大小使其一致
    Mat img1_resized, img2_resized, img3_resized;
    resize(img1, img1_resized, Size(400, 300));
    resize(img2, img2_resized, Size(400, 300));
    resize(img3, img3_resized, Size(400, 300));
    
    // 水平拼接
    hconcat(img1_resized, img2_resized, combined);
    Mat temp;
    hconcat(combined, img3_resized, temp);
    
    // 添加标题文字（可选）
    // putText(temp, title1, Point(10, 30), FONT_HERSHEY_SIMPLEX, 0.7, Scalar(0, 255, 0), 2);
    
    return temp;
}

/**
 * @brief 创建直方图对比可视化
 */
Mat createHistogramComparison(const Mat& img1, const Mat& img2, const Mat& img3,
                              const string& title1, const string& title2, const string& title3) {
    int histSize = 256;
    
    // 计算直方图
    Mat gray1, gray2, gray3;
    if (img1.channels() == 3) cvtColor(img1, gray1, COLOR_BGR2GRAY);
    else gray1 = img1;
    if (img2.channels() == 3) cvtColor(img2, gray2, COLOR_BGR2GRAY);
    else gray2 = img2;
    if (img3.channels() == 3) cvtColor(img3, gray3, COLOR_BGR2GRAY);
    else gray3 = img3;
    
    float range[] = {0, 256};
    const float* histRange = {range};
    
    Mat hist1, hist2, hist3;
    calcHist(&gray1, 1, 0, Mat(), hist1, 1, &histSize, &histRange, true, false);
    calcHist(&gray2, 1, 0, Mat(), hist2, 1, &histSize, &histRange, true, false);
    calcHist(&gray3, 1, 0, Mat(), hist3, 1, &histSize, &histRange, true, false);
    
    // 创建直方图图像
    int hist_w = 400;
    int hist_h = 300;
    int bin_w = cvRound((double)hist_w / histSize);
    
    Mat histImage(hist_h * 3, hist_w, CV_8UC3, Scalar(0, 0, 0));
    
    // 归一化
    normalize(hist1, hist1, 0, histImage.rows, NORM_MINMAX, -1, Mat());
    normalize(hist2, hist2, 0, histImage.rows, NORM_MINMAX, -1, Mat());
    normalize(hist3, hist3, 0, histImage.rows, NORM_MINMAX, -1, Mat());
    
    // 绘制第一个直方图
    for (int i = 0; i < histSize; i++) {
        rectangle(histImage, 
                  Point(i * bin_w, hist_h * 3 - 1),
                  Point((i + 1) * bin_w, hist_h * 3 - cvRound(hist1.at<float>(i))),
                  Scalar(255, 255, 255), -1, 8, 0);
    }
    
    // 添加标签
    putText(histImage, title1, Point(10, 20), FONT_HERSHEY_SIMPLEX, 0.5, Scalar(0, 255, 0), 1);
    putText(histImage, title2, Point(10, hist_h + 20), FONT_HERSHEY_SIMPLEX, 0.5, Scalar(0, 255, 255), 1);
    putText(histImage, title3, Point(10, hist_h * 2 + 20), FONT_HERSHEY_SIMPLEX, 0.5, Scalar(0, 0, 255), 1);
    
    // 绘制分隔线和标签指示器（简化版本）
    line(histImage, Point(0, hist_h), Point(hist_w, hist_h), Scalar(128, 128, 128), 1, 8);
    line(histImage, Point(0, hist_h * 2), Point(hist_w, hist_h * 2), Scalar(128, 128, 128), 1, 8);
    
    return histImage;
}

/**
 * @brief 演示不同直方图比较方法
 */
void demonstrateCompareMethods(const Mat& src1, const Mat& src2) {
    // 转换为灰度图
    Mat gray1, gray2;
    if (src1.channels() == 3) cvtColor(src1, gray1, COLOR_BGR2GRAY);
    else gray1 = src1.clone();
    if (src2.channels() == 3) cvtColor(src2, gray2, COLOR_BGR2GRAY);
    else gray2 = src2.clone();
    
    // 调整大小使其一致
    resize(gray2, gray2, gray1.size());
    
    // 计算直方图
    int histSize = 256;
    float range[] = {0, 256};
    const float* histRange = {range};
    
    Mat hist1, hist2;
    calcHist(&gray1, 1, 0, Mat(), hist1, 1, &histSize, &histRange, true, false);
    calcHist(&gray2, 1, 0, Mat(), hist2, 1, &histSize, &histRange, true, false);
    
    cout << "\n==============================================";
    cout << "\n    直方图比较方法演示";
    cout << "\n==============================================" << endl;
    
    // 1. 相关性比较 (Correlation)
    // 值范围: [-1, 1]，1 表示完美正相关（匹配）
    double corr = compareHist(hist1, hist2, HISTCMP_CORREL);
    cout << "\n1. 相关性比较 (HISTCMP_CORREL):" << endl;
    cout << "   结果: " << corr << endl;
    cout << "   解读: " << (corr > 0.9 ? "高度相似" : corr > 0.5 ? "中等相似" : "差异较大") << endl;
    
    // 2. 卡方比较 (Chi-Square)
    // 值范围: [0, +∞)，0 表示完美匹配
    double chi = compareHist(hist1, hist2, HISTCMP_CHISQR);
    cout << "\n2. 卡方比较 (HISTCMP_CHISQR):" << endl;
    cout << "   结果: " << chi << endl;
    cout << "   解读: " << (chi < 50 ? "相似度高" : chi < 200 ? "中等相似" : "差异较大") << endl;
    
    // 3. 交叉比较 (Intersection)
    // 值范围: [0, +∞)，值越大表示越匹配
    double inter = compareHist(hist1, hist2, HISTCMP_INTERSECT);
    cout << "\n3. 交叉比较 (HISTCMP_INTERSECT):" << endl;
    cout << "   结果: " << inter << endl;
    cout << "   解读: " << (inter > 0.9 * hist1.rows * hist1.cols ? "高度相似" : inter > 0.5 * hist1.rows * hist1.cols ? "中等相似" : "差异较大") << endl;
    
    // 4. Bhattacharyya 距离
    // 值范围: [0, 1]，0 表示完美匹配
    double bhatt = compareHist(hist1, hist2, HISTCMP_BHATTACHARYYA);
    cout << "\n4. Bhattacharyya 距离 (HISTCMP_BHATTACHARYYA):" << endl;
    cout << "   结果: " << bhatt << endl;
    cout << "   解读: " << (bhatt < 0.1 ? "高度相似" : bhatt < 0.3 ? "中等相似" : "差异较大") << endl;
    
    cout << "\n==============================================" << endl;
}

/**
 * @brief 生成测试图像（创建不同亮度的测试图）
 */
Mat generateTestImage(int width, int height, int type = 0) {
    Mat img(height, width, CV_8UC1);
    
    switch (type % 4) {
        case 0: // 均匀灰度
            img = Scalar(128);
            break;
        case 1: // 渐变
            for (int i = 0; i < height; i++) {
                for (int j = 0; j < width; j++) {
                    img.at<uchar>(i, j) = (i * 256 / height + j * 256 / width) / 2;
                }
            }
            break;
        case 2: // 高亮度
            img = Scalar(200);
            break;
        case 3: // 低亮度
            img = Scalar(50);
            break;
    }
    
    return img;
}

// ============================================================
// 主函数
// ============================================================
int main(int argc, char** argv) {
    cout << "============================================" << endl;
    cout << "  OpenCV C++ 直方图匹配算法演示" << endl;
    cout << "============================================" << endl;
    
    // ============================================================
    // 1. 使用内置测试图像进行演示
    // ============================================================
    cout << "\n[1] 使用测试图像进行演示..." << endl;
    
    // 创建三张测试图像（代表不同的亮度条件）
    Mat testImg1 = generateTestImage(400, 300, 0);  // 中等亮度
    Mat testImg2 = generateTestImage(400, 300, 1);  // 渐变
    Mat testImg3 = generateTestImage(400, 300, 2);  // 高亮度
    
    // 计算各图像直方图
    Mat hist1 = computeHistogram(testImg1);
    Mat hist2 = computeHistogram(testImg2);
    Mat hist3 = computeHistogram(testImg3);
    
    // 打印比较结果
    printComparisonResults(hist1, hist2, "testImg1", "testImg2");
    printComparisonResults(hist1, hist3, "testImg1", "testImg3");
    
    // ============================================================
    // 2. 直方图匹配演示
    // ============================================================
    cout << "\n[2] 直方图匹配演示..." << endl;
    
    // 创建源图像和目标图像
    Mat srcImage = generateTestImage(400, 300, 3);  // 低亮度
    Mat refImage = generateTestImage(400, 300, 0);  // 中等亮度
    
    // 执行直方图匹配
    Mat matchedImage = histogramMatching(srcImage, refImage);
    
    // 显示结果
    namedWindow("Source Image (Low Brightness)", WINDOW_NORMAL);
    namedWindow("Reference Image (Medium Brightness)", WINDOW_NORMAL);
    namedWindow("Matched Image (After Histogram Matching)", WINDOW_NORMAL);
    
    imshow("Source Image (Low Brightness)", srcImage);
    imshow("Reference Image (Medium Brightness)", refImage);
    imshow("Matched Image (After Histogram Matching)", matchedImage);
    
    // 绘制直方图对比
    Mat hist1_gray = computeHistogram(srcImage);
    Mat hist2_gray = computeHistogram(refImage);
    Mat hist_matched = computeHistogram(matchedImage);
    
    // 创建直方图可视化
    int hist_w = 512;
    int hist_h = 300;
    int bin_w = cvRound((double)hist_w / 256);
    
    Mat histImg(3 * hist_h, hist_w, CV_8UC3, Scalar(0, 0, 0));
    
    // 归一化直方图
    normalize(hist1_gray, hist1_gray, 0, histImg.rows, NORM_MINMAX, -1, Mat());
    normalize(hist2_gray, hist2_gray, 0, histImg.rows, NORM_MINMAX, -1, Mat());
    normalize(hist_matched, hist_matched, 0, histImg.rows, NORM_MINMAX, -1, Mat());
    
    // 绘制源图像直方图
    for (int i = 0; i < 256; i++) {
        line(histImg, 
             Point(i * bin_w, hist_h * 3 - 1),
             Point((i + 1) * bin_w, hist_h * 3 - cvRound(hist1_gray.at<float>(i))),
             Scalar(255, 0, 0), 2, 8, 0);
    }
    
    // 绘制参考图像直方图
    for (int i = 0; i < 256; i++) {
        line(histImg,
             Point(i * bin_w, hist_h * 2 - 1),
             Point((i + 1) * bin_w, hist_h * 2 - cvRound(hist2_gray.at<float>(i))),
             Scalar(0, 255, 0), 2, 8, 0);
    }
    
    // 绘制匹配后直方图
    for (int i = 0; i < 256; i++) {
        line(histImg,
             Point(i * bin_w, hist_h - 1),
             Point((i + 1) * bin_w, hist_h - cvRound(hist_matched.at<float>(i))),
             Scalar(0, 0, 255), 2, 8, 0);
    }
    
    // 添加标签
    putText(histImg, "Source Histogram (Red)", Point(10, 20), 
            FONT_HERSHEY_SIMPLEX, 0.6, Scalar(255, 0, 0), 1);
    putText(histImg, "Reference Histogram (Green)", Point(10, hist_h + 20), 
            FONT_HERSHEY_SIMPLEX, 0.6, Scalar(0, 255, 0), 1);
    putText(histImg, "Matched Histogram (Blue)", Point(10, hist_h * 2 + 20), 
            FONT_HERSHEY_SIMPLEX, 0.6, Scalar(0, 0, 255), 1);
    
    // 绘制分隔线
    line(histImg, Point(0, hist_h), Point(hist_w, hist_h), Scalar(128, 128, 128), 1);
    line(histImg, Point(0, hist_h * 2), Point(hist_w, hist_h * 2), Scalar(128, 128, 128), 1);
    
    namedWindow("Histogram Comparison", WINDOW_NORMAL);
    imshow("Histogram Comparison", histImg);
    
    // ============================================================
    // 3. 比较不同直方图比较方法
    // ============================================================
    cout << "\n[3] 直方图比较方法演示..." << endl;
    demonstrateCompareMethods(testImg1, testImg2);
    
    // ============================================================
    // 4. 等待按键结束
    // ============================================================
    cout << "\n[4] 按任意键退出..." << endl;
    waitKey(0);
    
    // 关闭所有窗口
    destroyAllWindows();
    
    cout << "\n程序结束。" << endl;
    return 0;
}